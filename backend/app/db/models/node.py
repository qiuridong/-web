"""Node ORM 模型 — `nodes` 表(执行节点,本地 + 远程 agent)。

MVP-1 远程 agent 架构,设计稿:`进度/设计/远程VPS脚本执行调研.md` § 7。

字段:id / slug(unique) / name / description / is_local /
      auth_token_hash(bcrypt) / last_seen_at / version /
      metadata_json / enabled / created_at / updated_at
索引:ix_nodes_slug (unique), ix_nodes_enabled

关系:instances(1:N)— Instance.node_id 反向引用(no cascade,删 node
      时若有 instance 引用应阻止;实际实现中 is_local 节点禁止删,
      其它节点删时检查是否仍有 instance 关联)

设计要点
--------
- `is_local=1` 的节点不可删,系统启动时自动 ensure 存在(slug='local', id=1)
- token 明文仅在创建 / regenerate 时返回**一次**(API 响应),DB 存 bcrypt
- last_seen_at 由 heartbeat / poll / result 三个 agent 端点更新
- metadata_json 存任意 JSON:IP / region / CPU / memory_mb / os / python_version 等
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.instance import Instance


class Node(Base):
    """执行节点(本地 / 远程 agent)。

    类比 GitHub Actions self-hosted runner 的 "runner" 概念。
    - is_local=True 节点 = 主面板自己(默认 id=1, slug='local'),无 token
    - 其它节点 = 远程 agent,需要分配 token + agent 主动 poll
    """

    __tablename__ = "nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_local: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    # bcrypt(token) - 仅 is_local=False 时有值
    auth_token_hash: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # 任意 JSON:IP / region / CPU / memory_mb / os 等
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1", index=True
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
    # instances 一对多;Instance.node_id FK 用 SET NULL 防引用方失踪
    # (实际删 node 前 service 层先检查 instance count)
    instances: Mapped[list[Instance]] = relationship(
        "Instance",
        back_populates="node",
        foreign_keys="Instance.node_id",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Node id={self.id} slug={self.slug!r} is_local={self.is_local}>"
