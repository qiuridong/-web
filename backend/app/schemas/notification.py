"""通知 schemas — Pydantic v2。

实现见 `进度/设计/后端架构.md` § 2.5 + § 1.5 + § 1.6。

模型清单
--------
渠道(channel)
  - ``ChannelListItem``      列表项(apprise_url_masked)
  - ``ChannelCreateRequest`` POST 请求
  - ``ChannelPatchRequest``  PATCH 请求(全字段可选)
  - ``ChannelTestRequest``   POST /test 请求
  - ``ChannelTestResponse``  POST /test 响应

规则(rule)
  - ``RuleListItem``         列表项
  - ``RuleCreateRequest``    POST 请求
  - ``RulePatchRequest``     PATCH 请求
  - ``RulePreviewResponse``  POST /preview 响应

所有 secret 字段(apprise_url 加密落库)都不直接出现在 GET 响应,
列表/详情用 ``apprise_url_masked``。
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ============================================================
# 共用枚举
# ============================================================
ScopeType = Literal["global", "script", "instance"]
EventType = Literal["success", "failure", "error", "timeout", "any"]


# ============================================================
# 渠道(channel)
# ============================================================
class ChannelBase(BaseModel):
    """渠道公共字段。"""

    name: str = Field(..., min_length=1, max_length=64)
    type: str = Field(default="apprise", min_length=1, max_length=32)
    description: str | None = Field(default=None, max_length=256)
    enabled: bool = Field(default=True)


class ChannelCreateRequest(ChannelBase):
    """``POST /notifications/channels`` 请求体。"""

    apprise_url: str = Field(
        ...,
        min_length=1,
        max_length=2048,
        description="apprise URL,如 tgram://botToken/chatId — 落库加密",
    )


class ChannelPatchRequest(BaseModel):
    """``PATCH /notifications/channels/{id}`` 请求体(全字段可选)。

    ``apprise_url`` 未传 = 保留原值。
    """

    name: str | None = Field(default=None, min_length=1, max_length=64)
    type: str | None = Field(default=None, min_length=1, max_length=32)
    description: str | None = Field(default=None, max_length=256)
    enabled: bool | None = None
    apprise_url: str | None = Field(
        default=None,
        min_length=1,
        max_length=2048,
        description="未传则保留原值",
    )


class ChannelListItem(BaseModel):
    """``GET /notifications/channels`` 列表项。

    ``apprise_url_masked`` 是脱敏后的展示值,如 ``tgram://***/***``。
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: str
    apprise_url_masked: str
    description: str | None = None
    enabled: bool
    last_test_at: datetime | None = None
    last_test_ok: bool | None = None
    created_at: datetime
    updated_at: datetime


class ChannelTestRequest(BaseModel):
    """``POST /notifications/channels/{id}/test`` 请求体。

    title/body 可省略,使用预置测试文本。
    """

    title: str | None = Field(default=None, max_length=128)
    body: str | None = Field(default=None, max_length=4096)


class ChannelTestResponse(BaseModel):
    """``POST /notifications/channels/{id}/test`` 响应。"""

    ok: bool
    latency_ms: float = Field(..., ge=0)
    error: str | None = None


# ============================================================
# 规则(rule)
# ============================================================
class RuleBase(BaseModel):
    """规则公共字段。"""

    name: str = Field(..., min_length=1, max_length=64)
    scope: ScopeType
    script_id: int | None = None
    instance_id: int | None = None
    event: EventType
    channel_id: int = Field(..., ge=1)
    template: str | None = Field(
        default=None,
        max_length=8192,
        description=(
            "Jinja2 模板;空 → 使用默认。"
            "若包含一行 `---`,上半为 title 模板,下半为 body 模板;"
            "否则整段当 body 模板,title 走默认。"
        ),
    )
    min_interval_sec: int = Field(default=0, ge=0, le=86400 * 30)
    enabled: bool = Field(default=True)


class RuleCreateRequest(RuleBase):
    """``POST /notifications/rules`` 请求体。

    scope 与 script_id / instance_id 的约束:
    - scope=global → 两者必空
    - scope=script → script_id 必填、instance_id 必空
    - scope=instance → 两者都必填(instance.script_id 必须等于 script_id;由 service 层校验)
    """

    @model_validator(mode="after")
    def _check_scope_consistency(self) -> RuleCreateRequest:
        if self.scope == "global":
            if self.script_id is not None or self.instance_id is not None:
                raise ValueError("scope=global 时 script_id / instance_id 必须为空")
        elif self.scope == "script":
            if self.script_id is None:
                raise ValueError("scope=script 时 script_id 必填")
            if self.instance_id is not None:
                raise ValueError("scope=script 时 instance_id 必须为空")
        elif self.scope == "instance":
            if self.script_id is None or self.instance_id is None:
                raise ValueError(
                    "scope=instance 时 script_id 与 instance_id 都必填"
                )
        return self


class RulePatchRequest(BaseModel):
    """``PATCH /notifications/rules/{id}`` 请求体(全字段可选)。

    若提供 ``scope``,与 script_id / instance_id 的一致性由 service 层结合
    DB 当前状态校验(允许只改 channel_id 等不动 scope 的局部更新)。
    """

    name: str | None = Field(default=None, min_length=1, max_length=64)
    scope: ScopeType | None = None
    script_id: int | None = None
    instance_id: int | None = None
    event: EventType | None = None
    channel_id: int | None = Field(default=None, ge=1)
    template: str | None = Field(default=None, max_length=8192)
    min_interval_sec: int | None = Field(default=None, ge=0, le=86400 * 30)
    enabled: bool | None = None


class RuleListItem(BaseModel):
    """``GET /notifications/rules`` 列表项 / 详情。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    scope: str
    script_id: int | None = None
    instance_id: int | None = None
    event: str
    channel_id: int
    template: str | None = None
    min_interval_sec: int
    last_fired_at: datetime | None = None
    enabled: bool
    created_at: datetime
    updated_at: datetime


class RulePreviewResponse(BaseModel):
    """``POST /notifications/rules/{id}/preview`` 响应。

    用假数据渲染一次,**不真发送**。
    """

    title: str
    body: str
