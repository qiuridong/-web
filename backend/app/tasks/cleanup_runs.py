"""按 ``settings.retention_days`` 清理旧 run 记录。

实现见 `进度/设计/后端架构.md` § 1.8 + § 2.4。

策略
----
- 周期触发(默认每天 03:00,由 scheduler 注册;若 6A 未接入则手动调用也可)
- 删除 ``started_at < now() - retention_days``,**保护活动 run**(pending/running)
- 修复 ``instances.last_run_id`` 若指向被删的行 → 重置为该实例最新一条 run
- 记录删除条数 + 重置数到应用日志

公开函数
--------
- ``run_cleanup_runs_task()`` — 周期任务入口(无参数,自己开 Session)
- ``run_cleanup_with_session(db, *, retention_days=None) -> tuple[int, int]`` —
  返回 ``(deleted, last_run_id_resets)``,便于测试

调度示例(6A 的 scheduler engine)::

    scheduler.add_job(
        run_cleanup_runs_task,
        trigger=CronTrigger(hour=3, minute=0),
        id="cleanup_runs",
        replace_existing=True,
    )
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.instance import Instance
from app.db.models.run import Run
from app.db.session import SessionLocal
from app.services import run_service, settings_service


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def run_cleanup_with_session(
    db: Session,
    *,
    retention_days: int | None = None,
) -> tuple[int, int]:
    """执行一次清理,返回 ``(deleted_count, last_run_id_resets)``。

    若 ``retention_days=None``,从 settings 读取(默认 30)。

    本函数会 ``db.commit()`` — 周期任务自己开 session。
    """
    if retention_days is None:
        retention_days = int(settings_service.get(db, "retention_days", 30) or 30)
    retention_days = max(1, int(retention_days))

    cutoff = _utcnow() - timedelta(days=retention_days)

    # 1) 先收集"将被删的 run ID 集合"用于修复 last_run_id 引用
    #    (避免 ON DELETE SET NULL 触发后失去信息)
    affected_run_ids = list(
        db.scalars(
            select(Run.id).where(
                Run.started_at < cutoff,
                Run.status.not_in(run_service.RUN_STATUS_ACTIVE),
            )
        ).all()
    )

    if not affected_run_ids:
        logger.info("cleanup_runs:无可清理记录 cutoff={}", cutoff.isoformat())
        return 0, 0

    # 2) 找出 instances 中 last_run_id 指向这些行的实例
    instances_with_stale_last_run = list(
        db.scalars(
            select(Instance).where(Instance.last_run_id.in_(affected_run_ids))
        ).all()
    )

    # 3) 删除
    deleted = run_service.cleanup_runs(db, before=cutoff)

    # 4) 修复:对每个受影响 instance,把 last_run_id 重置为最新的存活 run
    resets = 0
    for inst in instances_with_stale_last_run:
        latest_id = db.scalars(
            select(Run.id)
            .where(Run.instance_id == inst.id)
            .order_by(Run.started_at.desc())
            .limit(1)
        ).first()
        # 如果没有存活 run,清掉冗余字段
        if latest_id is None:
            inst.last_run_id = None
            inst.last_run_status = None
            inst.last_run_at = None
        else:
            inst.last_run_id = int(latest_id)
            latest_run = db.get(Run, int(latest_id))
            if latest_run is not None:
                inst.last_run_status = latest_run.status
                inst.last_run_at = latest_run.started_at
        resets += 1

    if resets:
        db.flush()

    db.commit()
    logger.info(
        "cleanup_runs 完成 cutoff={} deleted={} last_run_resets={}",
        cutoff.isoformat(),
        deleted,
        resets,
    )
    return deleted, resets


def run_cleanup_runs_task() -> None:
    """周期任务入口(无参,自动开/关 Session)。

    供 scheduler 直接注册;失败仅打日志,不抛(避免 scheduler 整体崩)。
    """
    db = SessionLocal()
    try:
        run_cleanup_with_session(db)
    except Exception as exc:  # noqa: BLE001
        logger.exception("cleanup_runs 任务异常 err={}", exc)
    finally:
        db.close()


# 兼容旧引用名(若 scheduler 直接 import 这个名字)
cleanup_runs_task = run_cleanup_runs_task
