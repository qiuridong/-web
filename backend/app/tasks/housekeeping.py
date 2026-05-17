"""杂项清理周期任务 — session 过期、failed_login_count 等。

实现见 `进度/设计/后端架构.md` § 5.3 + § 1.7。

每小时跑一次:
- 删除 sessions WHERE expires_at <= now()
- 重置 users.failed_login_count 若 locked_until 已过期

孤立 data_dir 清理留待 MVP-3(需要先把 instance.id 转 slug,再扫文件系统)。
"""
from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select, update

from app.db.models.user import User
from app.db.session import SessionLocal
from app.services import auth_service


def housekeeping_job() -> None:
    """每小时被 APScheduler 调用。"""
    try:
        with SessionLocal() as db:
            # session 过期清理
            deleted = auth_service.cleanup_expired_sessions(db)
            # users 锁定到期重置
            now = datetime.now(timezone.utc)
            stmt = select(User).where(
                User.locked_until.is_not(None),
                User.locked_until <= now,
            )
            unlocked = 0
            for user in db.scalars(stmt).all():
                user.locked_until = None
                user.failed_login_count = 0
                unlocked += 1
            db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("housekeeping_job 失败: {}", exc)
        return

    if deleted or unlocked:
        logger.info(
            "housekeeping 完成 expired_sessions={} unlocked_users={}",
            deleted,
            unlocked,
        )
