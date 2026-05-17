"""Script ORM 模型 — `scripts` 表(脚本插件元信息)。

实现见 `进度/设计/后端架构.md` § 1.2。

字段:id / slug(unique) / name / description / version / author / homepage /
      default_cron / default_timeout_sec / fields_schema_json /
      requires_secret / enabled / manifest_path / manifest_hash /
      last_scanned_at / created_at / updated_at
索引:ix_scripts_slug (unique), ix_scripts_enabled
关系:instances → 一对多,cascade="all, delete-orphan"
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.instance import Instance


class Script(Base):
    """脚本插件元数据。

    - 由"扫描 `scripts/` 目录"动作写入/更新
    - **不存储脚本源码本身**,只存可被前端展示和调度引用的元数据
    - 删除 = 从 DB 移除该插件登记,**不删磁盘文件**;下次扫描会重新发现
    - `fields_schema_json` 是从 manifest.yaml `fields:` 段解析得到的快照
    """

    __tablename__ = "scripts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[str] = mapped_column(
        String(32), nullable=False, default="0.0.0", server_default="0.0.0"
    )
    author: Mapped[str | None] = mapped_column(String(64), nullable=True)
    homepage: Mapped[str | None] = mapped_column(String(256), nullable=True)
    default_cron: Mapped[str | None] = mapped_column(String(64), nullable=True)
    default_timeout_sec: Mapped[int] = mapped_column(
        Integer, nullable=False, default=300, server_default="300"
    )
    # JSON 字段:SQLite 友好,存 Text(应用层 json.dumps/loads)
    fields_schema_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]", server_default="[]"
    )
    requires_secret: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1", index=True
    )
    manifest_path: Mapped[str] = mapped_column(String(512), nullable=False)
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    last_scanned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
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
    instances: Mapped[list[Instance]] = relationship(
        "Instance",
        back_populates="script",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Script id={self.id} slug={self.slug!r}>"
