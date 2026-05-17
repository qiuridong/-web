"""执行历史 service — 查询、清理、取消。

实现见 `进度/设计/后端架构.md` § 2.4 + § 4.4。

公开函数
--------
- ``list_runs(db, *, instance_id, script_slug, status, trigger_type,
              started_after, started_before, page, page_size)
   -> tuple[list[Run], int]``
- ``get_run(db, run_id) -> Run``                       # 含完整 stdout/stderr
- ``cancel_run(db, run_id, scheduler=None) -> Run``    # 仅 pending/running 可取消
- ``cleanup_runs(db, *, before=None, keep_days=None) -> int``   # 返回删除数

设计要点
--------
- 列表返回 ORM 实例,Pydantic 层裁剪字段(``RunListItem`` 不含 stdout/stderr/result_data_json)
- ``cancel_run`` 需要 scheduler;由路由层从 ``request.app.state.scheduler`` 取,
  传 ``None`` 时只翻 DB 状态(用于 6A 还没接入时的兜底)
- 错误统一抛 ``app.core.exceptions.*``
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from loguru import logger
from sqlalchemy import and_, delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import (
    RunNotFound,
    ValidationError,
)
from app.db.models.run import Run


# 状态分组(常量,便于复用)
RUN_STATUS_ACTIVE: tuple[str, ...] = ("pending", "running")
RUN_STATUS_TERMINAL: tuple[str, ...] = (
    "success",
    "failure",
    "error",
    "timeout",
    "cancelled",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ============================================================
# 列表
# ============================================================
def list_runs(
    db: Session,
    *,
    instance_id: int | None = None,
    script_slug: str | None = None,
    status: str | None = None,
    trigger_type: str | None = None,
    started_after: datetime | None = None,
    started_before: datetime | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Run], int]:
    """分页列表 + 多维筛选。

    所有筛选条件 AND 组合;按 ``started_at DESC`` 排序。
    返回 ``(items, total)``;调用方负责裁剪 stdout/stderr。
    """
    conds: list[Any] = []
    if instance_id is not None:
        conds.append(Run.instance_id == instance_id)
    if script_slug:
        conds.append(Run.script_slug == script_slug)
    if status:
        conds.append(Run.status == status)
    if trigger_type:
        conds.append(Run.trigger_type == trigger_type)
    if started_after is not None:
        conds.append(Run.started_at >= started_after)
    if started_before is not None:
        conds.append(Run.started_at < started_before)

    where_clause = and_(*conds) if conds else None

    count_stmt = select(func.count()).select_from(Run)
    # selectinload(Run.instance) — 避免列表渲染时按行 lazy-load instance(audit High #6)
    list_stmt = select(Run).options(selectinload(Run.instance))
    if where_clause is not None:
        count_stmt = count_stmt.where(where_clause)
        list_stmt = list_stmt.where(where_clause)

    total = int(db.execute(count_stmt).scalar_one())

    offset = max(0, (page - 1) * page_size)
    list_stmt = (
        list_stmt.order_by(Run.started_at.desc(), Run.id.desc())
        .offset(offset)
        .limit(page_size)
    )
    items = list(db.scalars(list_stmt).all())
    return items, total


# ============================================================
# 详情
# ============================================================
def get_run(db: Session, run_id: int) -> Run:
    """按 id 取单个 run;不存在抛 :class:`RunNotFound`。

    返回完整 ORM(含 stdout/stderr/result_data_json)。
    """
    run = db.get(Run, run_id)
    if run is None:
        raise RunNotFound(
            f"执行记录不存在: {run_id}",
            details={"run_id": run_id},
        )
    return run


# ============================================================
# 取消
# ============================================================
def cancel_run(
    db: Session,
    run_id: int,
    scheduler: Any | None = None,
) -> Run:
    """取消一个 pending/running 的 run。

    步骤
    ----
    1. 校验 run 存在
    2. 校验状态是 pending 或 running(否则 422)
    3. **若有 scheduler 且暴露了 ``cancel_run(run_id)`` 接口** — 调它发取消信号
       (scheduler/executor 内部应:对 running 子进程 SIGTERM → 5s → SIGKILL;
        对 pending 直接拒绝起进程)
    4. 翻 DB 状态为 ``cancelled``,补 ``finished_at`` / ``duration_ms``
       (executor 的"真正终止"也会再次写一遍,本调用幂等)
    5. 返回更新后的 Run

    ``scheduler=None`` 兜底:6A 尚未接入时仅翻状态,保证 API 可用。
    """
    run = get_run(db, run_id)
    if run.status not in RUN_STATUS_ACTIVE:
        raise ValidationError(
            f"当前状态 {run.status!r} 不可取消,只支持 pending / running",
            details={
                "run_id": run_id,
                "current_status": run.status,
                "allowed_status": list(RUN_STATUS_ACTIVE),
            },
        )

    # 1) 通知 scheduler/executor 真正停止子进程
    if scheduler is not None:
        cancel_fn = getattr(scheduler, "cancel_run", None)
        if callable(cancel_fn):
            try:
                cancel_fn(run_id)
            except Exception as exc:  # noqa: BLE001
                # 调度器内部错误不阻塞 DB 状态更新 — 至少 UI 看得到 cancelled
                logger.warning(
                    "scheduler.cancel_run 抛错(忽略),仅翻 DB 状态 run_id={} err={}",
                    run_id,
                    exc,
                )
        else:
            logger.debug(
                "scheduler 无 cancel_run 接口,仅翻 DB 状态 run_id={}", run_id
            )

    # 2) 翻 DB 状态
    now = _utcnow()
    run.status = "cancelled"
    if run.finished_at is None:
        run.finished_at = now
    if run.duration_ms is None and run.started_at is not None:
        # started_at 可能是 naive(SQLite),做一次兼容
        started = run.started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        delta = now - started
        run.duration_ms = max(0, int(delta.total_seconds() * 1000))
    db.flush()

    logger.info("取消 run run_id={} previous_status=via_status_check", run_id)
    return run


# ============================================================
# 清理
# ============================================================
def cleanup_runs(
    db: Session,
    *,
    before: datetime | None = None,
    keep_days: int | None = None,
) -> int:
    """删除符合条件的旧 run;返回实际删除数。

    必须传 ``before`` 或 ``keep_days`` 之一:

    - ``before``:删除 ``started_at < before`` 的所有 run
    - ``keep_days``:等价于 ``before = now - keep_days days``

    保护项:**正在执行**的 run(``status in pending/running``)永不删除,
    即使时间满足条件 — 防误删活动任务。

    本函数自身**不 commit**;路由层负责事务边界。
    """
    if before is None and keep_days is None:
        raise ValidationError(
            "cleanup_runs 需要 before 或 keep_days 之一",
            details={"field": "before|keep_days"},
        )

    cutoff: datetime
    if before is not None:
        cutoff = before
    else:
        # keep_days is not None
        cutoff = _utcnow() - timedelta(days=int(keep_days or 0))

    # 保护:不删活动状态
    stmt = delete(Run).where(
        Run.started_at < cutoff,
        Run.status.not_in(RUN_STATUS_ACTIVE),
    )
    result = db.execute(stmt)
    deleted = int(result.rowcount or 0)
    db.flush()
    if deleted:
        logger.info(
            "清理 runs 完成 cutoff={} deleted={}",
            cutoff.isoformat(),
            deleted,
        )
    return deleted
