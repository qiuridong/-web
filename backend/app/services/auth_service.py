"""鉴权 service — 纯业务逻辑,不依赖 FastAPI。

实现见 `进度/设计/后端架构.md` § 2.1 + § 5.3。

提供函数:
- `is_setup_required(db) -> bool`(用户表为空)
- `create_admin(db, username, password, display_name=None) -> User`
- `authenticate(db, username, password, ip, user_agent) -> tuple[User, str]`
- `verify_session(db, token) -> User`
- `revoke_session(db, token) -> None`
- `change_password(db, user, old_password, new_password) -> None`
- `revoke_all_other_sessions(db, user_id, current_token) -> int`
- `cleanup_expired_sessions(db) -> int`

所有失败抛 `app.core.exceptions.*` 子类,**不抛 HTTPException**。
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
from app.core.security import (
    generate_session_token,
    hash_password,
    verify_password,
)
from app.db.models.session import UserSession
from app.db.models.user import User

# v1 防爆破常量(后续可挪到 settings 表)
LOCKOUT_THRESHOLD = 5
LOCKOUT_MINUTES = 15


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ============================================================
# Setup / 创建管理员
# ============================================================
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
    """创建首个管理员账户。

    **二次检查**:并发场景下两个 setup 请求可能同时通过 `is_setup_required`,
    所以在事务内再查一次 count(==0 才允许 INSERT)。

    抛出
    ----
    - `ConflictError`:users 表已非空
    - `ValidationError`:参数缺失
    """
    if not username or not password:
        raise ValidationError("用户名和密码不能为空")

    # 二次检查 — 防 race
    count = db.execute(select(func.count()).select_from(User)).scalar_one()
    if count > 0:
        raise ConflictError(
            "系统已初始化,无法重复执行 setup",
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
    db.flush()  # 拿 id
    logger.info("创建管理员账户 user_id={} username={}", user.id, user.username)
    return user


# ============================================================
# 登录认证
# ============================================================
def authenticate(
    db: Session,
    *,
    username: str,
    password: str,
    ip: str | None = None,
    user_agent: str | None = None,
    ttl_hours: int = 24,
) -> tuple[User, str]:
    """校验用户名 + 密码,通过则返回 (user, session_token)。

    流程
    ----
    1. 按 username 查找
    2. 若锁定中 → AccountLocked
    3. 校验密码:
       - 失败:failed_login_count += 1;达到阈值 → 写 locked_until;抛 InvalidCredentials
       - 成功:重置 failed_login_count 与 locked_until;更新 last_login_*
    4. 写 sessions 行,返回 token

    为防止"用户名是否存在"被探测,**用户不存在与密码错误返回相同异常**(InvalidCredentials)。
    """
    if not username or not password:
        raise InvalidCredentials("用户名或密码错误")

    stmt = select(User).where(User.username == username)
    user = db.execute(stmt).scalar_one_or_none()

    now = _utcnow()

    # 用户不存在 — 不暴露
    if user is None:
        # 走一次假哈希以避免时间侧信道(粗粒度,真实业务量小可省)
        verify_password(password, "$2b$12$00000000000000000000000000000000000000000000000000000000")
        raise InvalidCredentials("用户名或密码错误")

    # 锁定中
    if user.locked_until is not None and user.locked_until > now:
        remaining = (user.locked_until - now).total_seconds()
        raise AccountLocked(
            "账户已被锁定,请稍后再试",
            details={
                "locked_until": user.locked_until.isoformat(),
                "retry_after_sec": int(remaining),
            },
        )

    # 校验密码
    if not verify_password(password, user.password_hash):
        user.failed_login_count = (user.failed_login_count or 0) + 1
        if user.failed_login_count >= LOCKOUT_THRESHOLD:
            user.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
            db.flush()
            logger.warning(
                "账户锁定 user_id={} username={} fails={} until={}",
                user.id,
                user.username,
                user.failed_login_count,
                user.locked_until,
            )
            raise AccountLocked(
                f"登录失败次数过多,已锁定 {LOCKOUT_MINUTES} 分钟",
                details={
                    "locked_until": user.locked_until.isoformat(),
                    "retry_after_sec": LOCKOUT_MINUTES * 60,
                },
            )
        db.flush()
        logger.info(
            "登录失败 user_id={} username={} fails={}",
            user.id,
            user.username,
            user.failed_login_count,
        )
        raise InvalidCredentials("用户名或密码错误")

    # 校验 is_active
    if not user.is_active:
        raise AccountLocked("账户已被禁用", details={"reason": "inactive"})

    # 通过 — 重置失败计数 + 更新最近登录
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    user.last_login_ip = ip

    # 写 session
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

    logger.info(
        "用户登录成功 user_id={} username={} session_id={} expires_at={}",
        user.id,
        user.username,
        session.id,
        expires_at.isoformat(),
    )
    return user, token


# ============================================================
# Session 校验 / 销毁
# ============================================================
def verify_session(db: Session, token: str | None) -> User:
    """校验 session token,返回所属 User。

    抛 `SessionExpired` 表示无效或过期。
    成功路径会顺手更新 `last_used_at`(批量优化以后再说)。
    """
    if not token:
        raise SessionExpired("未登录")

    stmt = select(UserSession).where(UserSession.token == token)
    session = db.execute(stmt).scalar_one_or_none()
    if session is None:
        raise SessionExpired("会话不存在或已失效")

    now = _utcnow()
    expires_at = session.expires_at
    # SQLite 经过 SQLAlchemy 反序列化后通常是 naive(UTC),做兼容
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at <= now:
        # 过期立即清理
        db.delete(session)
        db.flush()
        raise SessionExpired("会话已过期,请重新登录")

    # 更新 last_used_at(简单实现:每次都写;后续可改 30 秒粒度批量)
    session.last_used_at = now

    # 加载 user
    user = session.user
    if user is None or not user.is_active:
        raise SessionExpired("用户不存在或已被禁用")
    return user


def revoke_session(db: Session, token: str | None) -> None:
    """销毁单个 session(登出)。

    token 为空或 session 不存在时静默忽略(已是登出态)。
    """
    if not token:
        return
    db.execute(delete(UserSession).where(UserSession.token == token))
    db.flush()


# ============================================================
# 修改密码 / 撤销其他会话
# ============================================================
def change_password(
    db: Session,
    *,
    user: User,
    old_password: str,
    new_password: str,
) -> None:
    """校验旧密码 → bcrypt 新密码 → 撤销该用户**所有** session。

    调用方负责重新创建 session 并下发新 cookie(若需要)。
    本 service 不知道当前 token,因此撤销 *全部* session,强制所有客户端重新登录。
    """
    if not verify_password(old_password, user.password_hash):
        raise InvalidCredentials("旧密码不正确")
    if old_password == new_password:
        raise ValidationError(
            "新密码不能与旧密码相同",
            details={"field": "new_password"},
        )

    user.password_hash = hash_password(new_password)
    user.failed_login_count = 0
    user.locked_until = None
    db.flush()

    # 撤销所有 session
    deleted = db.execute(
        delete(UserSession).where(UserSession.user_id == user.id)
    )
    db.flush()
    logger.info(
        "用户改密 user_id={} 撤销 sessions={}",
        user.id,
        deleted.rowcount,
    )


def revoke_all_other_sessions(
    db: Session,
    *,
    user_id: int,
    current_token: str,
) -> int:
    """撤销除 current_token 外的所有 session,返回撤销数。"""
    res = db.execute(
        delete(UserSession).where(
            UserSession.user_id == user_id,
            UserSession.token != current_token,
        )
    )
    db.flush()
    return int(res.rowcount or 0)


# ============================================================
# Housekeeping
# ============================================================
def cleanup_expired_sessions(db: Session) -> int:
    """删除所有过期 session,返回删除数。

    供 `app/tasks/housekeeping.py` 周期调用。
    """
    now = _utcnow()
    res = db.execute(delete(UserSession).where(UserSession.expires_at <= now))
    db.flush()
    deleted = int(res.rowcount or 0)
    if deleted:
        logger.info("清理过期 session 数={}", deleted)
    return deleted
