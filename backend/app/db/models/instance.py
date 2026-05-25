"""Instance ORM 模型 — `instances` 表(脚本实例,调度的基本单位)。

实现见 `进度/设计/后端架构.md` § 1.3。

字段:id / script_id (FK scripts.id ON DELETE CASCADE) / name / description /
      cron_expr / timeout_sec / enabled / paused_until /
      config_blob (Fernet 加密) / config_version /
      max_retries / retry_interval_sec /
      last_run_id (FK runs.id ON DELETE SET NULL, 冗余) /
      last_run_status / last_run_at / next_run_at /
      total_runs / total_successes / created_at / updated_at
索引:ix_instances_script_id, ix_instances_enabled,
      ix_instances_next_run_at, ix_instances_script_enabled (script_id, enabled)
关系:script → 多对一;runs → 一对多 cascade
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
    from app.db.models.node import Node
    from app.db.models.run import Run
    from app.db.models.script import Script


class Instance(Base):
    """脚本实例。

    一个脚本可创建多个实例(典型场景:同一脚本管多个账号)。
    - `config_blob`:Fernet 加密后的 JSON,见 § 5.2;**模型层不自动加解密**,由 service 层
      调 `app.core.crypto` 处理
    - `last_run_*` 三个冗余字段在每次 run 结束后由调度器同步,避免列表页 N+1 join
    - 删除 instance 时级联删除其所有 runs
    - `node_id` (MVP-1):指定此实例在哪个节点执行;默认 1 = local(主面板自己)
    """

    __tablename__ = "instances"
    __table_args__ = (
        Index("ix_instances_script_enabled", "script_id", "enabled"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    script_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("scripts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # MVP-1 远程 agent:node_id 默认 1(local 节点)
    # ondelete=RESTRICT 太强(SQLite 不支持);用 SET NULL 后 service 层校验删 node 前先检查
    node_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("nodes.id", ondelete="SET NULL"),
        nullable=True,
        default=1,
        server_default="1",
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(String(256), nullable=True)
    cron_expr: Mapped[str | None] = mapped_column(String(64), nullable=True)
    timeout_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1", index=True
    )
    paused_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # 加密字段:存 Fernet base64 token,模型层不自动加解密
    config_blob: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    config_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    max_retries: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    retry_interval_sec: Mapped[int] = mapped_column(
        Integer, nullable=False, default=60, server_default="60"
    )
    # 冗余 last_run_* 字段:避免列表页 N+1 join
    # last_run_id 是 FK → runs.id,但 runs 表晚于 instances 创建,
    # use_alter=True + name 让 alembic 在两表都存在后用 ALTER TABLE 加 FK
    last_run_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("runs.id", ondelete="SET NULL", use_alter=True, name="fk_instances_last_run_id"),
        nullable=True,
    )
    last_run_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    total_runs: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    total_successes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
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
    script: Mapped[Script] = relationship("Script", back_populates="instances")
    # MVP-1:与 Node 关联,foreign_keys 显式指定避免 SQLAlchemy 报歧义
    node: Mapped[Node | None] = relationship(
        "Node",
        back_populates="instances",
        foreign_keys=[node_id],
    )
    runs: Mapped[list[Run]] = relationship(
        "Run",
        back_populates="instance",
        cascade="all, delete-orphan",
        order_by="Run.started_at.desc()",
        # 与 last_run_id 的 FK 区分:back_populates 用 instance_id 这一路
        foreign_keys="Run.instance_id",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Instance id={self.id} name={self.name!r} script_id={self.script_id}>"
