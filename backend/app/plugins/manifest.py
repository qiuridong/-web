"""manifest.yaml 解析与 schema 校验。

详见 `进度/设计/后端架构.md` § 3.1 / § 3.2。

公开接口:
- ``parse_manifest(path) -> Manifest``     从磁盘 yaml 文件读取并校验
- ``parse_manifest_text(text) -> Manifest`` 直接从字符串(测试/缓存场景)
- ``compute_hash(text) -> str``            SHA256 hex,用于 ``scripts.manifest_hash``
- ``ManifestField`` / ``ManifestRuntime`` / ``Manifest`` Pydantic 模型

校验失败统一抛 :class:`app.core.exceptions.ManifestInvalidError`,``details`` 字段
带 Pydantic 转换后的字段错误数组,便于前端定位。

字段类型(11 种)枚举: string / secret / integer / boolean / select / multiselect /
                       multiline / cron / url / json
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from apscheduler.triggers.cron import CronTrigger
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

# ============================================================
# 常量
# ============================================================
#: 字段类型枚举(§ 3.2 表;url 仅出现一次)
FIELD_TYPES: tuple[str, ...] = (
    "string",
    "secret",
    "integer",
    "boolean",
    "select",
    "multiselect",
    "multiline",
    "cron",
    "url",
    "json",
)

FieldType = Literal[
    "string",
    "secret",
    "integer",
    "boolean",
    "select",
    "multiselect",
    "multiline",
    "cron",
    "url",
    "json",
]

#: slug 正则:小写字母/数字开头,长度 1-63,允许 `-`(§ 1.2 + § 3.1)
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")

#: 字段 key 正则:小写字母开头,只允许 [a-z0-9_]
FIELD_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")

#: SemVer 简化版(允许 `1.2.3` / `1.2.3-rc1` / `1.2.3+build`),
#: 不严格执行 SemVer 2.0.0 — 业务只需要单调可比即可。
SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


# ============================================================
# 字段 option(select / multiselect 的子项)
# ============================================================
class FieldOption(BaseModel):
    """select / multiselect 字段的单个选项。"""

    model_config = ConfigDict(extra="forbid")

    value: str = Field(..., min_length=1, description="实际存储值")
    label: str = Field(..., min_length=1, description="UI 展示名")
    description: str | None = Field(default=None, description="可选,鼠标悬浮帮助")


# ============================================================
# 字段定义
# ============================================================
class ManifestField(BaseModel):
    """manifest.fields[*] 单个字段定义(§ 3.2)。

    用 ``model_config(extra="ignore")`` — 容忍未来新增的 type 特有属性,
    但 ``key`` / ``label`` / ``type`` 三个核心字段严格校验。
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    # ===== 通用属性 =====
    key: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    label: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    type: FieldType
    required: bool = False
    description: str | None = None
    placeholder: str | None = None
    group: str | None = None
    default: Any | None = None  # 各 type 自行解释

    # ===== string / secret / multiline 通用 =====
    min_length: int | None = Field(default=None, ge=0)
    max_length: int | None = Field(default=None, ge=1)
    pattern: str | None = None  # 正则字符串

    # ===== integer =====
    min: int | None = None
    max: int | None = None
    step: int | None = Field(default=None, ge=1)

    # ===== select / multiselect =====
    options: list[FieldOption] | None = None

    # ===== multiselect 特有 =====
    min_items: int | None = Field(default=None, ge=0)
    max_items: int | None = Field(default=None, ge=1)

    # ===== multiline =====
    rows: int | None = Field(default=None, ge=1, le=50)

    # ===== url =====
    schemes: list[str] | None = None

    # ===== json =====
    schema_: str | None = Field(default=None, alias="schema")

    # ---- 校验 ----
    @field_validator("key")
    @classmethod
    def _validate_key(cls, v: str) -> str:
        if not FIELD_KEY_RE.match(v):
            raise ValueError(
                f"字段 key 不合法 {v!r};必须以小写字母开头,只允许 [a-z0-9_]"
            )
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
        # 全部小写 + 去重保序
        seen: list[str] = []
        for s in v:
            s_low = s.lower()
            if s_low not in seen:
                seen.append(s_low)
        return seen

    @model_validator(mode="after")
    def _validate_type_specific(self) -> ManifestField:
        """type 特有字段的存在性 / 互斥校验。"""
        t = self.type

        # select / multiselect 必须给 options
        if t in {"select", "multiselect"} and not self.options:
            raise ValueError(f"{t} 字段必须提供 options 数组")

        # 非 select / multiselect 不应给 options
        if t not in {"select", "multiselect"} and self.options is not None:
            raise ValueError(f"{t} 字段不应包含 options")

        # min/max 仅 integer 有意义
        if t != "integer" and (self.min is not None or self.max is not None or self.step is not None):
            raise ValueError(f"{t} 字段不应包含 min/max/step")

        # min_length/max_length/pattern 仅 string-like 有意义
        if t not in {"string", "secret", "multiline"} and (
            self.min_length is not None or self.max_length is not None or self.pattern is not None
        ):
            raise ValueError(f"{t} 字段不应包含 min_length/max_length/pattern")

        # min_items/max_items 仅 multiselect
        if t != "multiselect" and (self.min_items is not None or self.max_items is not None):
            raise ValueError(f"{t} 字段不应包含 min_items/max_items")

        # rows 仅 multiline
        if t != "multiline" and self.rows is not None:
            raise ValueError(f"{t} 字段不应包含 rows")

        # schemes 仅 url
        if t != "url" and self.schemes is not None:
            raise ValueError(f"{t} 字段不应包含 schemes")

        # schema 仅 json
        if t != "json" and self.schema_ is not None:
            raise ValueError(f"{t} 字段不应包含 schema")

        # min/max 互逆校验
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError(f"min ({self.min}) > max ({self.max})")

        if (
            self.min_length is not None
            and self.max_length is not None
            and self.min_length > self.max_length
        ):
            raise ValueError(f"min_length ({self.min_length}) > max_length ({self.max_length})")

        if (
            self.min_items is not None
            and self.max_items is not None
            and self.min_items > self.max_items
        ):
            raise ValueError(f"min_items ({self.min_items}) > max_items ({self.max_items})")

        # cron 字段的 default 用 APScheduler 校验
        if t == "cron" and self.default is not None:
            if not isinstance(self.default, str):
                raise ValueError("cron 字段的 default 必须是字符串")
            try:
                CronTrigger.from_crontab(self.default)
            except (ValueError, KeyError) as exc:
                raise ValueError(f"cron 字段的 default 不是合法 cron 表达式: {exc}") from exc

        return self


# ============================================================
# runtime
# ============================================================
class ManifestRuntime(BaseModel):
    """manifest.runtime 块,所有字段都有默认值。"""

    model_config = ConfigDict(extra="ignore")

    python_version: str = Field(
        default=">=3.10",
        description="子进程使用的 Python 解释器版本要求(PEP 440 spec)",
    )
    isolated: bool = Field(default=True, description="false = 同进程 import(不推荐)")
    env_passthrough: list[str] = Field(
        default_factory=list,
        description="透传给子进程的环境变量名列表",
    )
    dependencies_file: str = Field(
        default="requirements.txt",
        description="若存在则 docker 镜像构建时安装",
    )


# ============================================================
# Manifest 顶层
# ============================================================
class Manifest(BaseModel):
    """完整 manifest.yaml 模型。"""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    # ===== 必填 =====
    slug: str
    name: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    version: str

    # ===== 可选 =====
    description: str | None = None
    author: Annotated[str, StringConstraints(max_length=64)] | None = None
    homepage: Annotated[str, StringConstraints(max_length=256)] | None = None

    default_cron: str | None = None
    default_timeout_sec: int = Field(default=300, ge=1, le=86400)
    icon: str = Field(default="icon.svg", description="相对路径,前端展示")

    fields: list[ManifestField] = Field(default_factory=list)
    runtime: ManifestRuntime = Field(default_factory=ManifestRuntime)

    @field_validator("slug")
    @classmethod
    def _validate_slug(cls, v: str) -> str:
        if not SLUG_RE.match(v):
            raise ValueError(
                f"slug 不合法 {v!r};必须匹配 [a-z0-9][a-z0-9-]{{0,62}}"
            )
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
        if v is None or v == "":
            return None
        try:
            CronTrigger.from_crontab(v)
        except (ValueError, KeyError) as exc:
            raise ValueError(f"default_cron 不是合法 cron 表达式: {exc}") from exc
        return v

    @model_validator(mode="after")
    def _validate_fields_unique(self) -> Manifest:
        """字段 key 必须唯一。"""
        seen: set[str] = set()
        for f in self.fields:
            if f.key in seen:
                raise ValueError(f"字段 key 重复: {f.key!r}")
            seen.add(f.key)
        return self

    # ---- 派生属性 ----
    @property
    def requires_secret(self) -> bool:
        """是否包含 secret 字段(用于冗余写入 ``scripts.requires_secret``)。"""
        return any(f.type == "secret" for f in self.fields)


# ============================================================
# 工具函数
# ============================================================
def parse_manifest_text(text: str, *, source: str | Path = "<string>") -> Manifest:
    """从字符串解析 manifest。

    :param text: yaml 文本
    :param source: 用于错误消息的来源标识(文件路径或 ``"<string>"``)
    :raises ManifestInvalidError: 解析或校验失败
    """
    # 1. yaml 解析
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ManifestInvalidError(
            message=f"manifest yaml 解析失败 ({source}): {exc}",
            details={"source": str(source), "yaml_error": str(exc)},
        ) from exc

    if not isinstance(raw, dict):
        raise ManifestInvalidError(
            message=f"manifest 顶层必须是 mapping,实际为 {type(raw).__name__} ({source})",
            details={"source": str(source)},
        )

    # 2. Pydantic 校验
    try:
        return Manifest(**raw)
    except ValidationError as exc:
        # 把 Pydantic 错误转成 details
        errors = [
            {
                "loc": ".".join(str(p) for p in e["loc"]),
                "msg": e["msg"],
                "type": e["type"],
            }
            for e in exc.errors()
        ]
        raise ManifestInvalidError(
            message=f"manifest 校验失败 ({source}): {len(errors)} 个错误",
            details={"source": str(source), "errors": errors},
        ) from exc


def parse_manifest(path: Path) -> Manifest:
    """从磁盘读取 manifest.yaml 并解析。

    :param path: manifest.yaml 文件绝对路径
    :raises ManifestInvalidError: 文件不存在 / yaml 错误 / schema 校验失败
    """
    path = Path(path)
    if not path.is_file():
        raise ManifestInvalidError(
            message=f"manifest 文件不存在: {path}",
            details={"path": str(path)},
        )
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ManifestInvalidError(
            message=f"manifest 文件读取失败 ({path}): {exc}",
            details={"path": str(path)},
        ) from exc
    return parse_manifest_text(text, source=path)


def compute_hash(text: str) -> str:
    """计算 manifest 文本的 SHA256 hex,用于 ``scripts.manifest_hash`` 增量同步。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
