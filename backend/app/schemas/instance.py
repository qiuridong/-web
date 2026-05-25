"""实例 API schemas — Pydantic v2。

实现见 `进度/设计/后端架构.md` § 2.3 + § 5.2。

模型清单
--------
- ``InstanceCreate``       POST /instances 请求体
- ``InstanceUpdate``       PATCH /instances/{id} 请求体(所有字段可选)
- ``InstanceListItem``     列表响应单项
- ``InstanceListResponse`` 列表响应包(items + 分页)
- ``InstanceDetail``       GET /instances/{id} 详情(含已脱敏 config + _secret_set)
- ``InstanceScriptBrief``  列表/详情中关联脚本的简要信息
- ``InstancePauseRequest`` POST /instances/{id}/pause 请求体
- ``InstanceRunResponse``  POST /instances/{id}/run 响应:`{ run_id }`
- ``InstanceTestResponse`` POST /instances/{id}/test 响应:RunResult 完整字段
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ============================================================
# 共用
# ============================================================
NAME_MIN = 1
NAME_MAX = 128
DESCRIPTION_MAX = 256
CRON_MAX = 64

#: 设计稿 § 1.3:max_retries 0..50 是合理上限(几乎没人会重试 50 次)
MAX_RETRIES_LIMIT = 50

#: retry_interval_sec 上限:60 * 60 * 24 = 86400(1 天)
RETRY_INTERVAL_LIMIT = 86400

#: timeout_sec 上限与脚本 manifest 保持一致
TIMEOUT_SEC_LIMIT = 86400


class InstanceScriptBrief(BaseModel):
    """实例详情/列表中关联脚本的简要信息(避免 N+1)。"""

    model_config = ConfigDict(from_attributes=True)

    slug: str
    name: str


# ============================================================
# 创建
# ============================================================
class InstanceCreate(BaseModel):
    """``POST /instances`` 请求体。

    设计稿 § 2.3:
    - ``script_slug`` 必填
    - ``cron_expr`` 留空则继承 ``script.default_cron``
    - ``timeout_sec`` 留空则继承 ``script.default_timeout_sec``
    - ``config`` 按 fields_schema 严格校验(service 层执行)
    """

    model_config = ConfigDict(extra="forbid")

    script_slug: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=NAME_MIN, max_length=NAME_MAX)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX)
    cron_expr: str | None = Field(default=None, max_length=CRON_MAX)
    timeout_sec: int | None = Field(default=None, ge=1, le=TIMEOUT_SEC_LIMIT)
    max_retries: int = Field(default=0, ge=0, le=MAX_RETRIES_LIMIT)
    retry_interval_sec: int = Field(default=60, ge=1, le=RETRY_INTERVAL_LIMIT)
    config: dict[str, Any] = Field(default_factory=dict)
    # MVP-1:绑定节点(默认 1 = local,主面板自己跑)
    node_id: int | None = Field(
        default=None,
        ge=1,
        description="节点 ID,默认 1 = local(主面板自身);"
        "选远程节点后,该实例的所有 run 都派发到该节点跑",
    )

    @field_validator("name", "description")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


# ============================================================
# 更新(所有字段可选)
# ============================================================
class InstanceUpdate(BaseModel):
    """``PATCH /instances/{id}`` 请求体 — 部分更新。

    关键语义(设计稿 § 5.2):
    - ``config`` 字段中**未提交的 secret 字段保持原值**(由 service 层用
      ``fields.merge_secrets`` 实现)
    - 其余非 secret 字段以新值覆盖(若提交)
    - ``script_slug`` 不允许改(改了等于换脚本,直接重建实例)
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=NAME_MIN, max_length=NAME_MAX)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX)
    cron_expr: str | None = Field(default=None, max_length=CRON_MAX)
    timeout_sec: int | None = Field(default=None, ge=1, le=TIMEOUT_SEC_LIMIT)
    max_retries: int | None = Field(default=None, ge=0, le=MAX_RETRIES_LIMIT)
    retry_interval_sec: int | None = Field(
        default=None, ge=1, le=RETRY_INTERVAL_LIMIT
    )
    enabled: bool | None = None
    config: dict[str, Any] | None = None
    # MVP-1:允许改节点(注意:**只改 DB,不动正在跑的 run**;下次触发才生效)
    node_id: int | None = Field(default=None, ge=1)

    @field_validator("name", "description")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


# ============================================================
# 暂停 / 立即触发
# ============================================================
class InstancePauseRequest(BaseModel):
    """``POST /instances/{id}/pause`` 请求体。

    设计稿 § 2.3:``{ until: ISO8601 }``,临时暂停到某时刻,到期自动恢复。
    """

    model_config = ConfigDict(extra="forbid")

    until: datetime = Field(
        ..., description="ISO 8601 时间戳;到此时刻自动 resume"
    )


class InstanceRunResponse(BaseModel):
    """``POST /instances/{id}/run`` 响应。"""

    run_id: int


# ============================================================
# 列表
# ============================================================
class InstanceListItem(BaseModel):
    """``GET /instances`` 列表响应单项。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    script: InstanceScriptBrief
    node_id: int | None = None  # MVP-1:实例绑定的节点 ID(1=local;None 兼容老数据)
    cron_expr: str | None = None
    timeout_sec: int | None = None
    enabled: bool
    paused_until: datetime | None = None
    last_run_id: int | None = None
    last_run_status: str | None = None
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    total_runs: int
    total_successes: int


class InstanceListResponse(BaseModel):
    """``GET /instances`` 完整响应。"""

    items: list[InstanceListItem]
    total: int
    page: int
    page_size: int


# ============================================================
# 详情
# ============================================================
class InstanceDetail(BaseModel):
    """``GET /instances/{id}`` 详情响应。

    关键(设计稿 § 5.2):
    - ``config`` 字段中 secret 字段值已置为 ``None``
    - ``_secret_set`` 标识每个 secret 字段是否已配置过非空值

    audit High #11:加 ``populate_by_name=True``,确保 service 层 ``model_validate``
    能接受 `secret_set` 或 `_secret_set` 两种键(防 alias 漂移)。响应仍走
    ``by_alias`` 输出为 ``_secret_set``。
    """

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )

    id: int
    name: str
    description: str | None = None
    script: InstanceScriptBrief
    node_id: int | None = None  # MVP-1:实例绑定的节点 ID(1=local;None 兼容老数据)
    cron_expr: str | None = None
    timeout_sec: int | None = None
    enabled: bool
    paused_until: datetime | None = None
    max_retries: int
    retry_interval_sec: int
    last_run_id: int | None = None
    last_run_status: str | None = None
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    total_runs: int
    total_successes: int
    created_at: datetime
    updated_at: datetime

    # —— 解密 + 脱敏后的字段 ——
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="config 字典;secret 字段已脱敏为 null",
    )
    secret_set: dict[str, bool] = Field(
        default_factory=dict,
        alias="_secret_set",
        description="secret 字段是否已配置过非空值",
    )


# ============================================================
# 试运行
# ============================================================
class InstanceTestResponse(BaseModel):
    """``POST /instances/{id}/test`` 响应。

    不写 runs 表,直接返回 sandbox 执行结果。
    """

    success: bool
    status: str = Field(
        ..., description="success / failure / error / timeout"
    )
    exit_code: int | None = None
    duration_ms: int | None = None
    result_message: str | None = None
    result_data: dict[str, Any] = Field(default_factory=dict)
    stdout: str | None = None
    stderr: str | None = None
    stdout_truncated: bool = False
    stderr_truncated: bool = False
