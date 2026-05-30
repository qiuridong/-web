"""APScheduler 封装 — 调度引擎 SchedulerService 单例。

实现见 `进度/设计/后端架构.md` § 4.1 - § 4.6 + § 9.2。

设计要点
--------
- 使用 ``AsyncIOScheduler + MemoryJobStore``(事实源是 ``instances`` 表)
- job_id 命名:``instance:{instance_id}`` 全局唯一
- 启动时全量加载所有 enabled + 未 paused 的 instance 注册
- CRUD 时增量同步:register / unregister / reschedule
- 暂停:pause 写 DB ``paused_until`` + scheduler.pause_job + 调度一次性 resume job
- cron 时区:``CronTrigger.from_crontab(expr, timezone=ZoneInfo(settings.tz))``
- 内置周期任务:scan_scripts / resume_paused / housekeeping(在 start 时注册)
  (cleanup_runs 留给 6B agent — 涉及 runs 表)

接口
----
- ``async start()``                  启动 + 全量加载 + 注册周期任务
- ``async shutdown(wait=True)``      优雅停止
- ``register(instance)``             新 instance 上线
- ``unregister(instance_id)``        删除/禁用
- ``reschedule(instance)``           更新 cron / timeout 等
- ``pause(instance_id, until)``      临时暂停
- ``resume(instance_id)``            立即恢复
- ``trigger_now(instance_id, ...)``  立即触发(走 executor)
- ``schedule_retry(...)``            executor 失败时回调安排 retry job
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger
from sqlalchemy import select

from app.config import get_settings
from app.db.models.instance import Instance
from app.db.session import SessionLocal
from app.scheduler.concurrency import reset_limiter
from app.scheduler.executor import (
    execute_run,
    terminate_active_process,
)

if TYPE_CHECKING:
    pass


# ============================================================
# 常量
# ============================================================
def _instance_job_id(instance_id: int) -> str:
    return f"instance:{instance_id}"


def _retry_job_id(instance_id: int, parent_run_id: int, attempt: int) -> str:
    return f"retry:{instance_id}:{parent_run_id}:{attempt}"


def _resume_job_id(instance_id: int) -> str:
    return f"resume:{instance_id}"


# 内置周期任务
_BUILTIN_JOBS = {
    "tasks:scan_scripts": "scripts/ 周期扫描",
    "tasks:resume_paused": "paused_until 到期恢复",
    "tasks:housekeeping": "session 过期 / 杂项清理",
    "tasks:node_health": "节点掉线检测 + 通知",
}


# ============================================================
# SchedulerService
# ============================================================
class SchedulerService:
    """APScheduler 包装 + 业务接口。

    单例,通过 ``app.state.scheduler`` 注入到 FastAPI。
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._scheduler: AsyncIOScheduler | None = None
        self._tz: ZoneInfo = self._make_tz(self._settings.tz)
        self._started: bool = False

    # ============================================================
    # 时区
    # ============================================================
    @staticmethod
    def _make_tz(tz_name: str) -> ZoneInfo:
        try:
            return ZoneInfo(tz_name)
        except Exception:  # noqa: BLE001
            logger.warning("时区 {} 无效,回退到 UTC", tz_name)
            return ZoneInfo("UTC")

    @property
    def tz(self) -> ZoneInfo:
        return self._tz

    # ============================================================
    # 生命周期
    # ============================================================
    @property
    def started(self) -> bool:
        return self._started

    @property
    def scheduler(self) -> AsyncIOScheduler:
        if self._scheduler is None:
            raise RuntimeError("Scheduler 尚未启动,请先调用 start()")
        return self._scheduler

    async def start(self) -> None:
        """启动:创建 scheduler、加载 enabled instance、注册周期任务。"""
        if self._started:
            return

        # 重置并发槽位(后续可读 DB settings.concurrent_runs_max)
        reset_limiter()

        self._scheduler = AsyncIOScheduler(
            jobstores={"default": MemoryJobStore()},
            timezone=self._tz,
            job_defaults={
                "coalesce": True,
                "max_instances": 1,  # 同一 instance 不重叠
                "misfire_grace_time": 60,
            },
        )
        self._scheduler.start()
        self._started = True
        logger.info("SchedulerService 启动 tz={}", self._settings.tz)

        # 注册内置周期任务
        self._register_builtin_tasks()

        # 全量加载 enabled + 未 paused 的 instance
        await self._load_enabled_instances()

    async def shutdown(self, wait: bool = True) -> None:
        """优雅停止。"""
        if not self._started or self._scheduler is None:
            return
        try:
            self._scheduler.shutdown(wait=wait)
        except Exception as exc:  # noqa: BLE001
            logger.warning("scheduler 关闭异常: {}", exc)
        self._started = False
        self._scheduler = None
        logger.info("SchedulerService 已关闭")

    # ============================================================
    # 加载 / 注册
    # ============================================================
    async def _load_enabled_instances(self) -> None:
        """启动时扫描所有 enabled 实例,注册到 scheduler。

        - paused_until 还在的:执行 pause + 调度 resume(交给 _maybe_register)
        - 没 cron 的:跳过
        """
        with SessionLocal() as db:
            instances = list(
                db.scalars(
                    select(Instance).where(Instance.enabled.is_(True))
                ).all()
            )
        count = 0
        for inst in instances:
            try:
                self._register_inner(inst)
                count += 1
            except Exception as exc:  # noqa: BLE001
                logger.error("注册 instance {} 失败: {}", inst.id, exc)
        logger.info(
            "已加载 {} / {} 个 enabled instance 到调度器", count, len(instances)
        )

    # ============================================================
    # 业务接口
    # ============================================================
    def register(self, instance: Instance) -> None:
        """注册或更新 instance 的 job。

        - instance.enabled = False → unregister
        - 无 cron → unregister
        - 有 cron + enabled → add/replace
        - paused_until 到期前 → pause job 并调度一次性 resume
        """
        if not self._started:
            return
        if not instance.enabled:
            self.unregister(instance.id)
            return
        self._register_inner(instance)

    def _register_inner(self, instance: Instance) -> None:
        cron = instance.cron_expr
        # 若 instance 自身没 cron,尝试继承 script.default_cron
        if not cron:
            # 这里我们没有 script 对象,只能再查一次
            # 为效率与简洁,从 DB 拉一下
            with SessionLocal() as db:
                from app.db.models.script import Script  # noqa: PLC0415

                script = db.get(Script, instance.script_id)
                if script is not None and script.default_cron:
                    cron = script.default_cron

        job_id = _instance_job_id(instance.id)

        if not cron:
            # 无 cron → 摘除 job(仅可手动触发)
            try:
                self.scheduler.remove_job(job_id)
            except Exception:  # noqa: BLE001
                pass
            return

        try:
            trigger = CronTrigger.from_crontab(cron, timezone=self._tz)
        except (ValueError, KeyError) as exc:
            logger.error(
                "instance {} cron_expr {!r} 不合法: {}",
                instance.id,
                cron,
                exc,
            )
            return

        self.scheduler.add_job(
            _scheduled_job_runner,
            trigger=trigger,
            id=job_id,
            args=[instance.id],
            replace_existing=True,
            misfire_grace_time=60,
            coalesce=True,
        )
        next_run = self._job_next_run(job_id)
        logger.info(
            "注册 instance.{} cron={!r} next={}",
            instance.id,
            cron,
            next_run,
        )

        # ===== audit High #4:把 next_run_time 回写到 instances.next_run_at =====
        # 注:这里在 _register_inner 一次性写;每次 cron 触发后 _scheduled_job_runner
        # 也会再写一次更新到下一次执行时间
        _write_instance_next_run_at(instance.id, next_run)

        # 处理 paused_until
        if instance.paused_until is not None:
            now = datetime.now(timezone.utc)
            until = instance.paused_until
            if until.tzinfo is None:
                until = until.replace(tzinfo=timezone.utc)
            if until > now:
                self._pause_job_until(instance.id, until)

    def unregister(self, instance_id: int) -> None:
        """从 scheduler 摘除 job(若有)。

        清空 ``instances.next_run_at`` 防止 dashboard 仍显示过期的下次执行时间。
        """
        if not self._started:
            return
        for jid in (
            _instance_job_id(instance_id),
            _resume_job_id(instance_id),
        ):
            try:
                self.scheduler.remove_job(jid)
            except Exception:  # noqa: BLE001
                pass
        # audit High #4:摘除 job 后清空 next_run_at
        _write_instance_next_run_at(instance_id, None)

    def reschedule(self, instance: Instance) -> None:
        """实例 cron/enabled 变化时调用。"""
        self.register(instance)

    def pause(self, instance_id: int, until: datetime) -> None:
        """暂停 instance 直到 ``until``;到期由 ``_resume_job_runner`` 自动恢复。"""
        if not self._started:
            return
        if until.tzinfo is None:
            until = until.replace(tzinfo=timezone.utc)
        self._pause_job_until(instance_id, until)

    def resume(self, instance_id: int) -> None:
        """立即恢复(清除 pause + resume job)。"""
        if not self._started:
            return
        try:
            self.scheduler.resume_job(_instance_job_id(instance_id))
        except Exception:  # noqa: BLE001
            pass
        try:
            self.scheduler.remove_job(_resume_job_id(instance_id))
        except Exception:  # noqa: BLE001
            pass

    def trigger_now(
        self,
        instance_id: int,
        *,
        trigger_type: str = "manual",
        trigger_user_id: int | None = None,
        pre_created_run_id: int | None = None,
    ) -> None:
        """立即触发一次执行(fire and forget)。

        在 scheduler 自己的 event loop 上排 task。
        从 sync FastAPI 路由(worker thread)与 cron job 回调(主 loop)
        都安全。
        """
        coro = execute_run(
            self,
            instance_id,
            trigger_type=trigger_type,
            trigger_user_id=trigger_user_id,
            pre_created_run_id=pre_created_run_id,
        )
        sched = self.scheduler
        loop = getattr(sched, "_eventloop", None)
        if loop is None:
            # AsyncIOScheduler 内部属性名在不同版本可能不同;兜底用当前 running loop
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError as exc:
                raise RuntimeError(
                    "Scheduler 未持有 event loop,trigger_now 失败"
                ) from exc

        # 判断当前线程是不是 loop 自己的线程:
        # - 是 → 直接 loop.create_task(coro)
        # - 不是(worker thread / 别的线程) → run_coroutine_threadsafe
        try:
            current = asyncio.get_running_loop()
        except RuntimeError:
            current = None

        if current is loop:
            loop.create_task(coro)
        else:
            asyncio.run_coroutine_threadsafe(coro, loop)

    def sync_next_run_at(self, instance_id: int) -> datetime | None:
        """从 APScheduler 取该 instance job 的 next_run_time 并回写 DB。

        audit High #4:之前 ``_register_inner`` 内部回写,但因为外层 service 还
        没 commit,新 session 查不到 instance → 写失败。改让路由层在 commit 后
        显式调本方法,确保 next_run_at 一定能写到 DB。

        :returns: 当前 next_run_time(已写入 DB);若 job 不存在返 None(同步清空)
        """
        if not self._started:
            return None
        next_run = self._job_next_run(_instance_job_id(instance_id))
        _write_instance_next_run_at(instance_id, next_run)
        return next_run

    def cancel_run(self, run_id: int) -> bool:
        """对 run_id 对应的活跃子进程发取消信号(SIGTERM → 5s → SIGKILL)。

        audit Critical #2:之前 ``cancel_run`` 只在 DB 翻 status,子进程仍在跑;
        现在通过 ``executor._ACTIVE_PROCESSES`` 注册表找到 proc,真正终止它。

        :returns:
            - ``True`` 若找到活跃进程且已对其发信号
            - ``False`` 若未找到(可能已自然退出)

        说明:本方法 sync,内部用 ``run_coroutine_threadsafe`` 把
        ``terminate_active_process(run_id)`` 排到 scheduler 自己的 event loop。
        若当前线程已是 loop 自己,直接 ``loop.create_task``。
        """
        if not self._started:
            return False

        # 先快速看 registry 里是否有这个 run_id 的活跃 proc
        # 若没有,直接返回 False,不必启 coroutine
        from app.scheduler.executor import get_active_process  # noqa: PLC0415

        if get_active_process(run_id) is None:
            return False

        sched = self._scheduler
        loop = getattr(sched, "_eventloop", None) if sched else None
        if loop is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                logger.warning(
                    "cancel_run: 无 event loop 可用 run_id={}", run_id
                )
                return False

        coro = terminate_active_process(run_id)

        # 判断当前是不是 loop 自己的线程
        try:
            current = asyncio.get_running_loop()
        except RuntimeError:
            current = None

        if current is loop:
            loop.create_task(coro)
        else:
            # 从 sync 线程(FastAPI worker thread)派到 loop 上执行,并等结果
            fut = asyncio.run_coroutine_threadsafe(coro, loop)
            try:
                # 等待至多 10 秒(SIGTERM grace 5s + SIGKILL grace 5s)
                return bool(fut.result(timeout=10.0))
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "cancel_run: 等待 terminate 超时/异常 run_id={} err={}",
                    run_id,
                    exc,
                )
                return False
        return True

    def schedule_retry(
        self,
        *,
        instance_id: int,
        parent_run_id: int,
        next_attempt: int,
        delay_sec: int,
    ) -> None:
        """安排一次性 retry job(executor 失败时回调)。"""
        if not self._started:
            return
        run_at = datetime.now(timezone.utc).timestamp() + max(1, int(delay_sec))
        trigger = DateTrigger(
            run_date=datetime.fromtimestamp(run_at, tz=timezone.utc)
        )
        jid = _retry_job_id(instance_id, parent_run_id, next_attempt)
        self.scheduler.add_job(
            _retry_job_runner,
            trigger=trigger,
            id=jid,
            args=[instance_id, parent_run_id, next_attempt],
            replace_existing=True,
            misfire_grace_time=60,
        )
        logger.info(
            "安排 retry job_id={} delay_sec={} attempt={}",
            jid,
            delay_sec,
            next_attempt,
        )

    # ============================================================
    # 内部
    # ============================================================
    def _pause_job_until(self, instance_id: int, until: datetime) -> None:
        try:
            self.scheduler.pause_job(_instance_job_id(instance_id))
        except Exception:  # noqa: BLE001
            pass
        # 安排一次性 resume
        try:
            self.scheduler.add_job(
                _resume_job_runner,
                trigger=DateTrigger(run_date=until),
                id=_resume_job_id(instance_id),
                args=[instance_id],
                replace_existing=True,
                misfire_grace_time=120,
            )
            logger.info(
                "instance.{} 暂停至 {} (resume job 已安排)", instance_id, until
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("安排 resume job 失败: {}", exc)

    def _job_next_run(self, job_id: str) -> datetime | None:
        try:
            job = self.scheduler.get_job(job_id)
            if job is None:
                return None
            return job.next_run_time
        except Exception:  # noqa: BLE001
            return None

    def _register_builtin_tasks(self) -> None:
        """注册周期内置任务。"""
        from app.tasks.housekeeping import housekeeping_job  # noqa: PLC0415
        from app.tasks.node_health import node_health_job  # noqa: PLC0415
        from app.tasks.resume_paused import resume_paused_job  # noqa: PLC0415
        from app.tasks.scan_scripts import scan_scripts_job  # noqa: PLC0415

        # scan_scripts — 5 分钟一次(script_scan_interval_sec)
        scan_interval = 300
        self.scheduler.add_job(
            scan_scripts_job,
            trigger=IntervalTrigger(seconds=scan_interval),
            id="tasks:scan_scripts",
            replace_existing=True,
            misfire_grace_time=120,
            coalesce=True,
        )

        # resume_paused — 每分钟扫一次
        self.scheduler.add_job(
            lambda: resume_paused_job(self),
            trigger=IntervalTrigger(minutes=1),
            id="tasks:resume_paused",
            replace_existing=True,
            misfire_grace_time=60,
            coalesce=True,
        )

        # housekeeping — 每小时
        self.scheduler.add_job(
            housekeeping_job,
            trigger=IntervalTrigger(hours=1),
            id="tasks:housekeeping",
            replace_existing=True,
            misfire_grace_time=120,
            coalesce=True,
        )

        # node_health — 每分钟扫节点掉线 + 告警(async job,await dispatch)
        self.scheduler.add_job(
            node_health_job,
            trigger=IntervalTrigger(minutes=1),
            id="tasks:node_health",
            replace_existing=True,
            misfire_grace_time=60,
            coalesce=True,
        )

        logger.info("内置周期任务已注册: {}", list(_BUILTIN_JOBS.keys()))


# ============================================================
# 顶层 job runner(APScheduler 要求可 pickle / 模块级)
# ============================================================
async def _scheduled_job_runner(instance_id: int) -> None:
    """APScheduler cron 触发的回调入口。

    触发后(无论执行结果)把"下次执行时间"回写到 ``instances.next_run_at``,
    确保 dashboard 始终显示真实的 next_run_at(audit High #4)。
    """
    from app.deps import get_scheduler_service  # noqa: PLC0415

    scheduler = get_scheduler_service()
    try:
        await execute_run(
            scheduler,
            instance_id,
            trigger_type="scheduled",
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "scheduled job 执行异常 instance_id={}: {}", instance_id, exc
        )
    finally:
        # 触发后,APScheduler 已计算出下一次执行时间(对 cron trigger 而言)。
        # 把它写回 DB,保证 dashboard 的"下次执行"永远反映真实状态。
        try:
            next_run = scheduler._job_next_run(_instance_job_id(instance_id))
            _write_instance_next_run_at(instance_id, next_run)
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "scheduled_job_runner: 回写 next_run_at 失败 instance={} err={}",
                instance_id,
                exc,
            )


async def _retry_job_runner(
    instance_id: int, parent_run_id: int, next_attempt: int
) -> None:
    """retry 一次性 job 回调。"""
    from app.deps import get_scheduler_service  # noqa: PLC0415

    scheduler = get_scheduler_service()
    try:
        await execute_run(
            scheduler,
            instance_id,
            trigger_type="retry",
            parent_run_id=parent_run_id,
            attempt=next_attempt,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "retry job 异常 instance_id={} attempt={}: {}",
            instance_id,
            next_attempt,
            exc,
        )


def _write_instance_next_run_at(
    instance_id: int, next_run: datetime | None
) -> None:
    """把 APScheduler 计算出的 next_run_time 写回 ``instances.next_run_at``。

    audit High #4:scheduler 之前从未回写此字段,导致 dashboard "下次执行" KPI
    永远显示 ``—``。此 helper 在 ``register / unregister / scheduled_job_runner``
    等关键节点被调用。

    设计要点:
    - 用独立 session,避免与外层 session 冲突
    - 异常静默(不影响调度主流程)
    - ``next_run = None`` 表示清空字段(典型场景:unregister)
    """
    try:
        # 归一化 tz(SQLite 存裸 datetime)
        if next_run is not None and next_run.tzinfo is None:
            next_run = next_run.replace(tzinfo=timezone.utc)
        with SessionLocal() as db:
            inst = db.get(Instance, instance_id)
            if inst is None:
                return
            if inst.next_run_at != next_run:
                inst.next_run_at = next_run
                db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.debug(
            "_write_instance_next_run_at 失败 instance_id={} err={}",
            instance_id,
            exc,
        )


def _resume_job_runner(instance_id: int) -> None:
    """paused_until 到期 — 清除 DB 字段 + resume scheduler job。"""
    from app.deps import get_scheduler_service  # noqa: PLC0415

    scheduler = get_scheduler_service()

    with SessionLocal() as db:
        inst = db.get(Instance, instance_id)
        if inst is not None and inst.paused_until is not None:
            inst.paused_until = None
            db.commit()
            logger.info("instance.{} paused_until 到期,已恢复", instance_id)
    try:
        scheduler.resume(instance_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("resume 失败 instance={}: {}", instance_id, exc)
