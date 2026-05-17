"""Session ORM 模型 — `sessions` 表(登录态)。

实现见 `进度/设计/后端架构.md` § 5.3。

字段:id / user_id (FK users.id ON DELETE CASCADE) / token (unique) /
      created_at / expires_at / last_used_at / ip / user_agent
索引:ix_sessions_token (unique), ix_sessions_user_id

类名为 `UserSession` — 避免与 SQLAlchemy 的 `sqlalchemy.orm.Session` 冲突。
表名仍为 `sessions`(对齐设计稿)。
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.user import User


class UserSession(Base):
    """服务端会话记录。

    Cookie 名 `sid`,token = `secrets.token_urlsafe(48)`。
    每次请求中间件查 session;过期/不存在 → 401。
    登出 = 服务端删行 + 客户端清 cookie。
    """

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # ===== 关系 =====
    user: Mapped[User] = relationship("User", back_populates="sessions")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<UserSession id={self.id} user_id={self.user_id}>"
