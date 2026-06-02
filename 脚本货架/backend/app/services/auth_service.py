"""鉴权 service（移植自主项目 ``backend/app/services/auth_service.py``）。

纯业务逻辑，不依赖 FastAPI。所有失败抛 ``app.core.exceptions.*`` 子类。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from loguru import logger
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.exceptions import (
    AccountLocked,
    ConflictError,
    InvalidCredentials,
    SessionExpired,
    ValidationError,
)
from app.core.security import generate_session_token, hash_password, verify_password
from app.db.models.session import UserSession
from app.db.models.user import User

LOCKOUT_THRESHOLD = 5
LOCKOUT_MINUTES = 15


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def is_setup_required(db: Session) -> bool:
    """users 表为空 → 需要首次 setup。"""
    count = db.execute(select(func.count()).select_from(User)).scalar_one()
    return count == 0


def create_admin(
    db: Session,
    *,
    username: str,
    password: str,
    display_name: str | None = None,
) -> User:
    """创建首个管理员账户（事务内二次检查防 race）。"""
    if not username or not password:
        raise ValidationError("用户名和密码不能为空")

    count = db.execute(select(func.count()).select_from(User)).scalar_one()
    if count > 0:
        raise ConflictError(
            "系统已初始化，无法重复执行 setup",
            details={"existing_user_count": int(count)},
        )

    user = User(
        username=username,
        password_hash=hash_password(password),
        display_name=display_name,
        is_active=True,
        is_admin=True,
    )
    db.add(user)
    db.flush()
    logger.info("创建管理员账户 user_id={} username={}", user.id, user.username)
    return user


def authenticate(
    db: Session,
    *,
    username: str,
    password: str,
    ip: str | None = None,
    user_agent: str | None = None,
    ttl_hours: int = 24,
) -> tuple[User, str]:
    """校验用户名 + 密码，通过则返回 (user, session_token)。"""
    if not username or not password:
        raise InvalidCredentials("用户名或密码错误")

    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    now = _utcnow()

    if user is None:
        verify_password(password, "$2b$12$00000000000000000000000000000000000000000000000000000000")
        raise InvalidCredentials("用户名或密码错误")

    if user.locked_until is not None and user.locked_until > now:
        remaining = (user.locked_until - now).total_seconds()
        raise AccountLocked(
            "账户已被锁定，请稍后再试",
            details={"locked_until": user.locked_until.isoformat(), "retry_after_sec": int(remaining)},
        )

    if not verify_password(password, user.password_hash):
        user.failed_login_count = (user.failed_login_count or 0) + 1
        if user.failed_login_count >= LOCKOUT_THRESHOLD:
            user.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
            db.flush()
            logger.warning("账户锁定 user_id={} fails={}", user.id, user.failed_login_count)
            raise AccountLocked(
                f"登录失败次数过多，已锁定 {LOCKOUT_MINUTES} 分钟",
                details={"locked_until": user.locked_until.isoformat(), "retry_after_sec": LOCKOUT_MINUTES * 60},
            )
        db.flush()
        raise InvalidCredentials("用户名或密码错误")

    if not user.is_active:
        raise AccountLocked("账户已被禁用", details={"reason": "inactive"})

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    user.last_login_ip = ip

    token = generate_session_token()
    expires_at = now + timedelta(hours=ttl_hours)
    session = UserSession(
        user_id=user.id,
        token=token,
        created_at=now,
        expires_at=expires_at,
        last_used_at=now,
        ip=ip,
        user_agent=(user_agent or "")[:256] or None,
    )
    db.add(session)
    db.flush()
    logger.info("用户登录成功 user_id={} username={}", user.id, user.username)
    return user, token


def verify_session(db: Session, token: str | None) -> User:
    """校验 session token，返回所属 User；无效/过期抛 ``SessionExpired``。"""
    if not token:
        raise SessionExpired("未登录")

    session = db.execute(
        select(UserSession).where(UserSession.token == token)
    ).scalar_one_or_none()
    if session is None:
        raise SessionExpired("会话不存在或已失效")

    now = _utcnow()
    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at <= now:
        db.delete(session)
        db.flush()
        raise SessionExpired("会话已过期，请重新登录")

    session.last_used_at = now
    user = session.user
    if user is None or not user.is_active:
        raise SessionExpired("用户不存在或已被禁用")
    return user


def revoke_session(db: Session, token: str | None) -> None:
    """销毁单个 session（登出）。"""
    if not token:
        return
    db.execute(delete(UserSession).where(UserSession.token == token))
    db.flush()


def cleanup_expired_sessions(db: Session) -> int:
    """删除所有过期 session，返回删除数。"""
    now = _utcnow()
    res = db.execute(delete(UserSession).where(UserSession.expires_at <= now))
    db.flush()
    return int(res.rowcount or 0)
