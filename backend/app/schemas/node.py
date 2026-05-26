"""节点 schemas — Pydantic v2。

MVP-1 远程 agent,设计稿:`进度/设计/远程VPS脚本执行调研.md` § 7。

模型清单
--------
- ``NodeListItem``       列表响应单项(含 online 状态)
- ``NodeListResponse``   列表响应包
- ``NodeDetail``         详情响应
- ``NodeCreate``         POST /nodes 请求体
- ``NodeUpdate``         PATCH /nodes/{id} 请求体
- ``NodeCreateResponse`` POST /nodes 响应(含一次性明文 token)
- ``NodeTokenResponse``  POST /nodes/{id}/regenerate-token 响应

- ``AgentPollResponse``   GET /agent/poll 响应(有任务 / 无任务)
- ``AgentTaskPayload``    poll 命中时返回的 task 详情(给 agent 用)
- ``AgentResultRequest``  POST /agent/runs/{run_id}/result
- ``AgentStdoutRequest``  POST /agent/runs/{run_id}/stdout(增量)
- ``AgentHeartbeatRequest`` POST /agent/heartbeat
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ============================================================
# admin 端 schemas
# ============================================================
SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")


class NodeListItem(BaseModel):
    """节点列表项 — 含 online 派生字段。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str | None = None
    description: str | None = None
    is_local: bool
    last_seen_at: datetime | None = None
    version: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    enabled: bool
    online: bool = False
    created_at: datetime
    updated_at: datetime


class NodeListResponse(BaseModel):
    """节点列表响应。"""

    items: list[NodeListItem]
    total: int


class NodeDetail(NodeListItem):
    """节点详情(目前与列表项字段一致;预留扩展)。"""

    pass


class NodeCreate(BaseModel):
    """``POST /nodes`` 请求体。"""

    model_config = ConfigDict(extra="forbid")

    slug: str = Field(..., min_length=1, max_length=64)
    name: str | None = Field(default=None, max_length=128)
    description: str | None = Field(default=None, max_length=512)

    @field_validator("slug")
    @classmethod
    def _check_slug(cls, v: str) -> str:
        if not SLUG_PATTERN.fullmatch(v):
            raise ValueError(
                "slug 必须以小写字母/数字开头,只含小写字母/数字/连字符"
            )
        return v


class NodeUpdate(BaseModel):
    """``PATCH /nodes/{id}`` 请求体。"""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=128)
    description: str | None = Field(default=None, max_length=512)
    enabled: bool | None = None


class NodeCreateResponse(BaseModel):
    """创建节点的响应 — **含一次性明文 token**。

    重要:``token`` 仅此一次返回,前端必须显示给用户保存。
    后续无法再取(DB 只存 bcrypt hash)。
    """

    node: NodeDetail
    token: str = Field(
        ...,
        description="agent 长期 token 明文。仅此一次返回,丢失后只能 regenerate。",
    )


class NodeTokenResponse(BaseModel):
    """重新生成 token 的响应。"""

    token: str = Field(..., description="新明文 token。仅此一次返回。")


# ============================================================
# Agent 端 schemas
# ============================================================
class AgentTaskPayload(BaseModel):
    """agent poll 命中时返回的 task 数据 — 包含 sandbox 跑脚本所需所有信息。

    设计:agent 收到后构造 sandbox_runner.py 的 stdin JSON 执行。
    """

    model_config = ConfigDict(extra="forbid")

    run_id: int
    instance_id: int
    instance_name: str
    script_slug: str
    script_version: str | None = None
    timeout_sec: int
    trigger_type: str
    attempt: int = 1
    # 解密后的明文 config(包含 secret 字段)— 主面板解密下发,agent 不存
    config: dict[str, Any] = Field(default_factory=dict)
    # 给 agent 的 env passthrough 提示(白名单变量名)
    env_passthrough: list[str] = Field(default_factory=list)


class PendingActions(BaseModel):
    """节点待处理指令(主面板 → agent 的"推送"机制,通过 poll piggyback)。

    - ``sync``:agent 应该拉这些 slug(调 ``_ensure_script_synced``)
    - ``delete``:agent 应该删本地 ``scripts/<slug>/``

    主面板把 ``nodes.pending_actions`` JSON 反序列化后,**非空时**附在 poll
    response 里;agent 处理完调 ``/agent/inventory-report`` ack。
    """

    model_config = ConfigDict(extra="forbid")

    sync: list[str] = Field(default_factory=list)
    delete: list[str] = Field(default_factory=list)


class AgentPollResponse(BaseModel):
    """``GET /agent/poll?wait=30`` 响应。

    - 有任务:``{"task": {...}, "pending_actions": null|{...}}``
    - 无任务:``{"task": null, "pending_actions": null|{...}}``(等了 wait 秒返回)

    无论有无 task,**都会捎带 pending_actions**(若非空)— 这是主面板向 agent
    "推送" 的唯一通道(agent pull only,无 push)。
    """

    model_config = ConfigDict(extra="forbid")

    task: AgentTaskPayload | None = None
    pending_actions: PendingActions | None = None


class AgentInventoryReport(BaseModel):
    """``POST /agent/inventory-report`` 请求体 — agent 主动报告本地情况 + ack。

    时机:
    - agent 启动后第一次 sanity check 通过
    - agent 处理完 ``pending_actions`` 中的 sync/delete 之后
    - 兜底周期(可选,如每 5 min 一次)

    Agent 报告 ``deployed_scripts``(本地实际有的 slug → sha256)+
    ``acked_actions``(刚处理完哪些);主面板更新 ``nodes.deployed_scripts``
    + 从 ``nodes.pending_actions`` 移除 acked 的 entry。
    """

    model_config = ConfigDict(extra="forbid")

    deployed_scripts: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description='{"slug": {"sha256": "...", "deployed_at": "ISO"}}',
    )
    acked_actions: PendingActions = Field(
        default_factory=PendingActions,
        description="agent 刚处理完的 sync/delete slug,主面板从 pending_actions 移除",
    )


class AgentInventoryResponse(BaseModel):
    """``POST /agent/inventory-report`` 响应。"""

    model_config = ConfigDict(extra="forbid")

    ok: bool = True
    pending_actions_after: PendingActions = Field(
        default_factory=PendingActions,
        description="ack 之后**剩余**的 pending_actions(可能有新加的,告诉 agent 还要做)",
    )


class AgentResultRequest(BaseModel):
    """``POST /agent/runs/{run_id}/result`` 请求体。

    agent 跑完 sandbox 后回传的终态。
    """

    model_config = ConfigDict(extra="forbid")

    success: bool
    status: str = Field(
        ...,
        description="success / failure / error / timeout / cancelled",
    )
    exit_code: int | None = None
    duration_ms: int | None = None
    message: str = Field(default="", max_length=512)
    data: dict[str, Any] = Field(default_factory=dict)
    stdout: str | None = None
    stderr: str | None = None
    stdout_truncated: bool = False
    stderr_truncated: bool = False


class AgentStdoutRequest(BaseModel):
    """``POST /agent/runs/{run_id}/stdout`` 请求体。

    增量上报 stdout / stderr,主面板转发给 SSE 订阅者 + append 到 ``runs.stdout``。
    """

    model_config = ConfigDict(extra="forbid")

    stream: str = Field(..., description='"stdout" / "stderr"')
    lines: list[str] = Field(..., description="该批次的多行文本(已 rstrip)")
    seq: int = Field(
        default=0,
        description="agent 端单调递增序号(防丢包/乱序;v1 仅记录不强校验)",
    )

    @field_validator("stream")
    @classmethod
    def _check_stream(cls, v: str) -> str:
        if v not in ("stdout", "stderr"):
            raise ValueError("stream 必须是 'stdout' 或 'stderr'")
        return v


class AgentHeartbeatRequest(BaseModel):
    """``POST /agent/heartbeat`` 请求体。"""

    model_config = ConfigDict(extra="forbid")

    version: str | None = Field(default=None, max_length=32)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentHeartbeatResponse(BaseModel):
    """``POST /agent/heartbeat`` 响应。"""

    model_config = ConfigDict(extra="forbid")

    ok: bool = True
    server_time: datetime
    node_id: int
    node_slug: str
