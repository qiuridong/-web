"""执行历史 schemas — Pydantic v2。

实现见 `进度/设计/后端架构.md` § 2.4 + § 1.4。

模型清单
--------
- ``RunListItem``         列表项(不含 stdout/stderr/result_data_json)
- ``RunListResponse``     列表包(items + total + page + page_size)
- ``RunDetail``           详情(含完整 stdout/stderr/result_data + 截断标记)
- ``RunCleanupRequest``   清理请求({ before } 或 { keep_days })
- ``RunCleanupResponse``  清理响应({ deleted: N })
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ============================================================
# 列表
# ============================================================
class RunListItem(BaseModel):
    """``GET /runs`` 列表响应单项。

    **不含** ``stdout`` / ``stderr`` / ``result_data_json`` — 列表只展示摘要。
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    instance_id: int
    script_slug: str
    trigger_type: str
    trigger_user_id: int | None = None
    parent_run_id: int | None = None
    status: str
    exit_code: int | None = None
    result_message: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    duration_ms: int | None = None
    host: str | None = None


class RunListResponse(BaseModel):
    """``GET /runs`` 完整响应。"""

    items: list[RunListItem]
    total: int
    page: int
    page_size: int


# ============================================================
# 详情
# ============================================================
class RunDetail(BaseModel):
    """``GET /runs/{id}`` 详情响应,含完整 stdout/stderr。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    instance_id: int
    script_slug: str
    trigger_type: str
    trigger_user_id: int | None = None
    parent_run_id: int | None = None
    status: str
    exit_code: int | None = None
    result_message: str | None = None
    result_data: dict[str, Any] | None = Field(
        default=None,
        description="result_data_json 反序列化后的对象;脚本失败或未输出则为 None",
    )
    stdout: str | None = None
    stderr: str | None = None
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    started_at: datetime
    finished_at: datetime | None = None
    duration_ms: int | None = None
    host: str | None = None
    created_at: datetime


# ============================================================
# 清理
# ============================================================
class RunCleanupRequest(BaseModel):
    """``DELETE /runs/cleanup`` 请求体。

    二选一(必填)::

        { "before": "2026-04-01T00:00:00Z" }   # 删除该时间之前的所有 run
        { "keep_days": 30 }                    # 仅保留最近 N 天

    两者都传时优先 ``before``;两者都不传抛 422。
    """

    model_config = ConfigDict(extra="forbid")

    before: datetime | None = Field(
        default=None,
        description="删除 started_at < before 的所有 run(ISO 8601)",
    )
    keep_days: int | None = Field(
        default=None,
        ge=0,
        le=3650,
        description="保留最近 N 天 — 等价于 before = now - N days",
    )

    @model_validator(mode="after")
    def _at_least_one(self) -> RunCleanupRequest:
        if self.before is None and self.keep_days is None:
            raise ValueError("必须提供 before 或 keep_days 之一")
        return self


class RunCleanupResponse(BaseModel):
    """``DELETE /runs/cleanup`` 响应。"""

    deleted: int = Field(..., ge=0, description="实际删除的行数")
