"""脚本相关 schema + 从 ORM 行构造响应的工具。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.db.models.script import HubScript


class FieldSummary(BaseModel):
    key: str
    label: str
    type: str
    required: bool = False


class ScriptListItem(BaseModel):
    slug: str
    name: str
    description: str | None = None
    version: str
    author: str | None = None
    homepage: str | None = None
    tags: list[str] = []
    field_count: int = 0
    file_count: int = 0
    size_bytes: int = 0
    download_count: int = 0
    has_icon: bool = False
    updated_at: datetime


class ScriptDetail(ScriptListItem):
    manifest_yaml: str
    fields_summary: list[FieldSummary] = []
    bundle_sha256: str = ""
    icon_svg: str | None = None
    created_at: datetime


class FileItem(BaseModel):
    path: str
    size: int
    editable: bool


class FileListResponse(BaseModel):
    slug: str
    files: list[FileItem]


class FileContentResponse(BaseModel):
    slug: str
    path: str
    content: str


class WriteFileRequest(BaseModel):
    content: str


class UploadResponse(BaseModel):
    slug: str
    name: str
    version: str
    created: bool


class UpdateScriptRequest(BaseModel):
    tags: list[str] | None = None


# ===== ORM → schema =====
def list_item_from_row(row: HubScript) -> ScriptListItem:
    return ScriptListItem(
        slug=row.slug,
        name=row.name,
        description=row.description,
        version=row.version,
        author=row.author,
        homepage=row.homepage,
        tags=list(row.tags or []),
        field_count=len(row.fields_summary or []),
        file_count=row.file_count,
        size_bytes=row.size_bytes,
        download_count=row.download_count,
        has_icon=bool(row.icon_svg),
        updated_at=row.updated_at,
    )


def detail_from_row(row: HubScript) -> ScriptDetail:
    base = list_item_from_row(row).model_dump()
    return ScriptDetail(
        **base,
        manifest_yaml=row.manifest_yaml,
        fields_summary=[FieldSummary(**f) for f in (row.fields_summary or [])],
        bundle_sha256=row.bundle_sha256,
        icon_svg=row.icon_svg,
        created_at=row.created_at,
    )
