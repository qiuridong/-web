"""脚本 API schemas(Pydantic v2)。

详见 `进度/设计/后端架构.md` § 2.2 / § 3.1-3.2。

模型清单:
- ``ScriptListItem``      列表响应单项
- ``ScriptListResponse``  列表响应包(items + 分页)
- ``ScriptDetail``        详情响应(含 fields_schema、readme、icon_url、requirements_present)
- ``ScanResultResponse``  扫描响应:added/updated/removed/errors
- ``ScanError``           扫描中单个失败项
- ``ScriptOption``        select/multiselect 选项(字段 schema 输出)
- ``FieldDefinition``     字段 schema 单项(给前端渲染表单用)
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ScriptOption(BaseModel):
    """select / multiselect 选项(详情响应 fields_schema 中)。"""

    model_config = ConfigDict(extra="ignore")
    value: str
    label: str
    description: str | None = None


class FieldDefinition(BaseModel):
    """字段 schema 单项 — 详情响应给前端渲染表单。

    与 :class:`app.plugins.manifest.ManifestField` 字段一致,但去掉内部 alias
    并保证 JSON 友好(无 Python None 默认隐藏)。
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    key: str
    label: str
    type: str
    required: bool = False
    description: str | None = None
    placeholder: str | None = None
    group: str | None = None
    default: Any | None = None

    # type-specific
    min_length: int | None = None
    max_length: int | None = None
    pattern: str | None = None
    min: int | None = None
    max: int | None = None
    step: int | None = None
    options: list[ScriptOption] | None = None
    min_items: int | None = None
    max_items: int | None = None
    rows: int | None = None
    schemes: list[str] | None = None
    json_schema: str | None = Field(default=None, alias="schema")


class ScriptListItem(BaseModel):
    """``GET /scripts`` 列表响应单项。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str
    description: str | None = None
    version: str
    default_cron: str | None = None
    enabled: bool
    requires_secret: bool = False
    instance_count: int = 0
    last_scanned_at: datetime


class ScriptListResponse(BaseModel):
    """``GET /scripts`` 完整响应,带分页元信息。"""

    items: list[ScriptListItem]
    total: int
    page: int
    page_size: int


class ScriptDetail(BaseModel):
    """``GET /scripts/{slug}`` 详情响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str
    description: str | None = None
    version: str
    author: str | None = None
    homepage: str | None = None
    default_cron: str | None = None
    default_timeout_sec: int
    enabled: bool
    requires_secret: bool = False
    instance_count: int = 0
    manifest_path: str
    manifest_hash: str
    last_scanned_at: datetime
    created_at: datetime
    updated_at: datetime

    # —— 解析后的额外字段 ——
    fields_schema: list[FieldDefinition] = Field(
        default_factory=list,
        description="manifest.fields 解析后的数组,前端按此渲染表单",
    )
    readme_md: str | None = Field(default=None, description="README.md 原文(若存在)")
    requirements_present: bool = Field(
        default=False, description="requirements.txt 是否存在"
    )
    icon_url: str | None = Field(
        default=None,
        description="icon 静态访问 URL(``/static/scripts/<slug>/<icon_rel>``);若文件缺失则为 None",
    )


class ScanError(BaseModel):
    """扫描期间单个脚本目录的失败信息。"""

    slug: str
    error: str


class ScanResultResponse(BaseModel):
    """``POST /scripts/scan`` 响应。"""

    added: list[str] = Field(default_factory=list)
    updated: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    errors: list[ScanError] = Field(default_factory=list)
