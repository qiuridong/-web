"""通知相关 ORM — `notification_channels` + `notification_rules` 两张表。

实现见 `进度/设计/后端架构.md` § 1.5、§ 1.6。

NotificationChannel(§ 1.5):
  字段:id / name (unique) / type / apprise_url_blob (Fernet 加密) /
        enabled / description / last_test_at / last_test_ok /
        created_at / updated_at
  索引:ix_notification_channels_name (unique), ix_notification_channels_enabled
  关系:rules → cascade

NotificationRule(§ 1.6):
  字段:id / name / scope (global/script/instance) /
        script_id (FK scripts.id ON DELETE CASCADE, nullable) /
        instance_id (FK instances.id ON DELETE CASCADE, nullable) /
        event (success/failure/error/timeout/any) /
        channel_id (FK notification_channels.id ON DELETE CASCADE) /
        template / min_interval_sec / last_fired_at /
        enabled / created_at / updated_at
  索引:ix_rules_scope_lookup (scope, script_id, instance_id, event, enabled)
  约束(应用层校验):scope=script ⇒ script_id 必填、instance_id 必空;
                    scope=instance ⇒ 两者都必填且 instance.script_id == script_id
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.instance import Instance
    from app.db.models.script import Script


class NotificationChannel(Base):
    """通知渠道。

    `apprise_url_blob` 是 Fernet 加密后的 apprise URL,如 `tgram://bottoken/ChatID`。
    GET 响应自动脱敏为 `<scheme>://***/***` 形式(scheme 暴露便于识别渠道类型)。
    """

    __tablename__ = "notification_channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="apprise", server_default="apprise"
    )
    # 加密字段:存 Fernet base64 token,模型层不自动加解密
    apprise_url_blob: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1", index=True
    )
    description: Mapped[str | None] = mapped_column(String(256), nullable=True)
    last_test_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_test_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # ===== 关系 =====
    rules: Mapped[list[NotificationRule]] = relationship(
        "NotificationRule",
        back_populates="channel",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<NotificationChannel id={self.id} name={self.name!r}>"


class NotificationRule(Base):
    """通知规则。

    匹配优先级:
    - 默认所有命中且 enabled 的规则都触发各自渠道(多渠道并发)
    - 若多条规则命中**同一渠道**,取 scope 更具体的一条(instance > script > global)避免重复推送

    复合索引 `ix_rules_scope_lookup` 用于一次扫描完成匹配。
    """

    __tablename__ = "notification_rules"
    __table_args__ = (
        Index(
            "ix_rules_scope_lookup",
            "scope",
            "script_id",
            "instance_id",
            "event",
            "enabled",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    script_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("scripts.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    instance_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("instances.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    event: Mapped[str] = mapped_column(String(16), nullable=False)
    channel_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("notification_channels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    template: Mapped[str | None] = mapped_column(Text, nullable=True)
    min_interval_sec: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_fired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # ===== 关系 =====
    channel: Mapped[NotificationChannel] = relationship(
        "NotificationChannel", back_populates="rules"
    )
    script: Mapped[Script | None] = relationship("Script")
    instance: Mapped[Instance | None] = relationship("Instance")

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<NotificationRule id={self.id} name={self.name!r} scope={self.scope}>"
        )
