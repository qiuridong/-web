"""hub_scripts 表 — 货架脚本元数据。

源文件落在 ``data/scripts/<slug>/``（结构同管家 scripts/），本表只存元数据 +
manifest 原文 + bundle 摘要。``compute_script_bundle`` 实时从源目录打 zip。
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class HubScript(Base):
    __tablename__ = "hub_scripts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    author: Mapped[str | None] = mapped_column(String(64), nullable=True)
    homepage: Mapped[str | None] = mapped_column(String(256), nullable=True)
    #: icon.svg 文件内容（内联文本，前端直接渲染）
    icon_svg: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: 标签数组（用户分类，如 ["PT", "漫画"]）
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    #: manifest.yaml 原文（详情页展示 / 重新解析）
    manifest_yaml: Mapped[str] = mapped_column(Text, nullable=False)
    #: 从 manifest 抽取的字段摘要 [{key,label,type,required}]（列表/详情快速展示）
    fields_summary: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    file_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bundle_sha256: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    download_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow, nullable=False
    )
