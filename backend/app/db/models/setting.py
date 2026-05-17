"""Setting ORM 模型 — `settings` 表(全局 KV)。

实现见 `进度/设计/后端架构.md` § 1.8。

字段:key (PK) / value_json / description / is_secret /
      updated_at / updated_by (FK users.id ON DELETE SET NULL)

预置 key 清单(应用启动时若不存在则插入默认):见 § 1.8 表格
- retention_days = 30
- timezone = Asia/Shanghai
- default_timeout_sec = 300
- default_max_log_bytes = 262144
- concurrent_runs_max = 4
- notify_on_first_failure_only = false
- script_scan_on_startup = true
- script_scan_interval_sec = 300
- session_ttl_hours = 24
- lockout_threshold = 5
- lockout_minutes = 15
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.user import User


class Setting(Base):
    """全局 KV 配置。

    - `key` 是 PK,值统一以 JSON 编码(`value_json`),支持任意类型
    - `is_secret` 标记敏感项(API 自动脱敏)
    - 写入时记录 `updated_by`(谁改的)
    """

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value_json: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(String(256), nullable=True)
    is_secret: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    updated_by: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ===== 关系 =====
    updater: Mapped[User | None] = relationship("User", foreign_keys=[updated_by])

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Setting key={self.key!r}>"
