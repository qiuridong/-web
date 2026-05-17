"""恢复 paused_until 到期的 instance — 兜底周期任务。

实现见 `进度/设计/后端架构.md` § 4.3 (pause/resume)。

策略:
- 每分钟扫一次 instances WHERE paused_until <= now()
- 清空 paused_until 字段
- 调用 scheduler.resume(instance_id)
- 兜底:即便 pause 时安排的"一次性 resume job"漏触发,也能由本任务补救
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from loguru import logger
from sqlalchemy import select

from app.db.models.instance import Instance
from app.db.session import SessionLocal

if TYPE_CHECKING:
    from app.scheduler.engine import SchedulerService


def resume_paused_job(scheduler: "SchedulerService | None" = None) -> None:
    """扫描 paused_until 已到期的 instance,清字段 + 通知 scheduler。"""
    now = datetime.now(timezone.utc)
    try:
        with SessionLocal() as db:
            stmt = select(Instance).where(
                Instance.paused_until.is_not(None),
                Instance.paused_until <= now,
            )
            expired = list(db.scalars(stmt).all())
            resumed_ids: list[int] = []
            for inst in expired:
                inst.paused_until = None
                resumed_ids.append(inst.id)
            if expired:
                db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("resume_paused_job 扫描失败: {}", exc)
        return

    if not expired:
        return

    if scheduler is not None:
        for iid in resumed_ids:
            try:
                scheduler.resume(iid)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "resume_paused_job: scheduler.resume({}) 失败: {}", iid, exc
                )

    logger.info("resume_paused_job 恢复 {} 个实例 ids={}", len(resumed_ids), resumed_ids)
