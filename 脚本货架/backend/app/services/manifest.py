"""manifest.yaml 解析与 schema 校验（精简自主项目 ``backend/app/plugins/manifest.py``）。

与管家**保持同样的 slug / version / 字段校验口径**，以确保货架入库的脚本
未来能被管家原样接受。唯一差异：**不校验 cron 语法**（货架不运行脚本，cron
合法性是管家运行时的职责），从而去掉 apscheduler 依赖。

公开接口：
- ``parse_manifest_text(text) -> Manifest``
- ``parse_manifest(path) -> Manifest``
- ``compute_hash(text) -> str``
- ``summarize_fields(manifest) -> list[dict]``  抽取字段摘要供前端
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)

from app.core.exceptions import ManifestInvalidError

FIELD_TYPES: tuple[str, ...] = (
    "string", "secret", "integer", "boolean", "select",
    "multiselect", "multiline", "cron", "url", "json",
)

FieldType = Literal[
    "string", "secret", "integer", "boolean", "select",
    "multiselect", "multiline", "cron", "url", "json",
]

#: slug 正则（与管家一致）：小写字母/数字开头，长度 1-63，允许 ``-``
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
#: 字段 key 正则：小写字母开头，只允许 [a-z0-9_]
FIELD_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
#: SemVer 简化版（与管家一致）
SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


class FieldOption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)
    description: str | None = None


class ManifestField(BaseModel):
    """manifest.fields[*] 单个字段定义。"""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    key: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    label: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    type: FieldType
    required: bool = False
    description: str | None = None
    placeholder: str | None = None
    group: str | None = None
    default: Any | None = None

    min_length: int | None = Field(default=None, ge=0)
    max_length: int | None = Field(default=None, ge=1)
    pattern: str | None = None

    min: int | None = None
    max: int | None = None
    step: int | None = Field(default=None, ge=1)

    options: list[FieldOption] | None = None
    min_items: int | None = Field(default=None, ge=0)
    max_items: int | None = Field(default=None, ge=1)
    rows: int | None = Field(default=None, ge=1, le=50)
    schemes: list[str] | None = None
    schema_: str | None = Field(default=None, alias="schema")

    @field_validator("key")
    @classmethod
    def _validate_key(cls, v: str) -> str:
        if not FIELD_KEY_RE.match(v):
            raise ValueError(f"字段 key 不合法 {v!r}；必须以小写字母开头，只允许 [a-z0-9_]")
        return v

    @field_validator("pattern")
    @classmethod
    def _validate_pattern(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            re.compile(v)
        except re.error as exc:
            raise ValueError(f"pattern 不是合法正则: {exc}") from exc
        return v

    @field_validator("schemes")
    @classmethod
    def _validate_schemes(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        if not v:
            raise ValueError("schemes 数组不能为空")
        seen: list[str] = []
        for s in v:
            if s.lower() not in seen:
                seen.append(s.lower())
        return seen

    @model_validator(mode="after")
    def _validate_type_specific(self) -> ManifestField:
        t = self.type
        if t in {"select", "multiselect"} and not self.options:
            raise ValueError(f"{t} 字段必须提供 options 数组")
        if t not in {"select", "multiselect"} and self.options is not None:
            raise ValueError(f"{t} 字段不应包含 options")
        if t != "integer" and (self.min is not None or self.max is not None or self.step is not None):
            raise ValueError(f"{t} 字段不应包含 min/max/step")
        if t not in {"string", "secret", "multiline"} and (
            self.min_length is not None or self.max_length is not None or self.pattern is not None
        ):
            raise ValueError(f"{t} 字段不应包含 min_length/max_length/pattern")
        if t != "multiselect" and (self.min_items is not None or self.max_items is not None):
            raise ValueError(f"{t} 字段不应包含 min_items/max_items")
        if t != "multiline" and self.rows is not None:
            raise ValueError(f"{t} 字段不应包含 rows")
        if t != "url" and self.schemes is not None:
            raise ValueError(f"{t} 字段不应包含 schemes")
        if t != "json" and self.schema_ is not None:
            raise ValueError(f"{t} 字段不应包含 schema")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError(f"min ({self.min}) > max ({self.max})")
        if (self.min_length is not None and self.max_length is not None
                and self.min_length > self.max_length):
            raise ValueError(f"min_length ({self.min_length}) > max_length ({self.max_length})")
        if (self.min_items is not None and self.max_items is not None
                and self.min_items > self.max_items):
            raise ValueError(f"min_items ({self.min_items}) > max_items ({self.max_items})")
        # 货架不校验 cron 语法，仅要求 default 是字符串
        if t == "cron" and self.default is not None and not isinstance(self.default, str):
            raise ValueError("cron 字段的 default 必须是字符串")
        return self


class ManifestRuntime(BaseModel):
    model_config = ConfigDict(extra="ignore")
    python_version: str = Field(default=">=3.10")
    isolated: bool = Field(default=True)
    env_passthrough: list[str] = Field(default_factory=list)
    dependencies_file: str = Field(default="requirements.txt")


class Manifest(BaseModel):
    """完整 manifest.yaml 模型。"""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    slug: str
    name: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    version: str

    description: str | None = None
    author: Annotated[str, StringConstraints(max_length=64)] | None = None
    homepage: Annotated[str, StringConstraints(max_length=256)] | None = None

    default_cron: str | None = None
    default_timeout_sec: int = Field(default=300, ge=1, le=86400)
    icon: str = Field(default="icon.svg")

    fields: list[ManifestField] = Field(default_factory=list)
    runtime: ManifestRuntime = Field(default_factory=ManifestRuntime)

    @field_validator("slug")
    @classmethod
    def _validate_slug(cls, v: str) -> str:
        if not SLUG_RE.match(v):
            raise ValueError(f"slug 不合法 {v!r}；必须匹配 [a-z0-9][a-z0-9-]{{0,62}}")
        return v

    @field_validator("version")
    @classmethod
    def _validate_version(cls, v: str) -> str:
        if not SEMVER_RE.match(v):
            raise ValueError(f"version {v!r} 不是合法 SemVer")
        return v

    @field_validator("default_cron")
    @classmethod
    def _validate_default_cron(cls, v: str | None) -> str | None:
        # 货架不校验 cron 语法（管家运行时校验），空串归一为 None
        return v or None

    @model_validator(mode="after")
    def _validate_fields_unique(self) -> Manifest:
        seen: set[str] = set()
        for f in self.fields:
            if f.key in seen:
                raise ValueError(f"字段 key 重复: {f.key!r}")
            seen.add(f.key)
        return self

    @property
    def requires_secret(self) -> bool:
        return any(f.type == "secret" for f in self.fields)


def parse_manifest_text(text: str, *, source: str | Path = "<string>") -> Manifest:
    """从字符串解析 manifest，失败抛 :class:`ManifestInvalidError`。"""
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ManifestInvalidError(
            f"manifest yaml 解析失败 ({source}): {exc}",
            details={"source": str(source), "yaml_error": str(exc)},
        ) from exc

    if not isinstance(raw, dict):
        raise ManifestInvalidError(
            f"manifest 顶层必须是 mapping，实际为 {type(raw).__name__} ({source})",
            details={"source": str(source)},
        )

    try:
        return Manifest(**raw)
    except ValidationError as exc:
        errors = [
            {"loc": ".".join(str(p) for p in e["loc"]), "msg": e["msg"], "type": e["type"]}
            for e in exc.errors()
        ]
        raise ManifestInvalidError(
            f"manifest 校验失败 ({source}): {len(errors)} 个错误",
            details={"source": str(source), "errors": errors},
        ) from exc


def parse_manifest(path: Path) -> Manifest:
    """从磁盘读取 manifest.yaml 并解析。"""
    path = Path(path)
    if not path.is_file():
        raise ManifestInvalidError(f"manifest 文件不存在: {path}", details={"path": str(path)})
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ManifestInvalidError(
            f"manifest 文件读取失败 ({path}): {exc}", details={"path": str(path)}
        ) from exc
    return parse_manifest_text(text, source=path)


def compute_hash(text: str) -> str:
    """manifest 文本 SHA256 hex。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def summarize_fields(manifest: Manifest) -> list[dict[str, Any]]:
    """抽取字段摘要供前端列表/详情展示。"""
    return [
        {"key": f.key, "label": f.label, "type": f.type, "required": f.required}
        for f in manifest.fields
    ]
