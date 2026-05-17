"""仪表盘 schemas — Pydantic v2。

实现见 `进度/设计/后端架构.md` § 2.7。

模型清单
--------
- ``OverviewScripts``        / ``OverviewInstances`` / ``OverviewRuns24h``
- ``DashboardOverview``      ``GET /dashboard/overview`` 响应
- ``UpcomingItem``           ``GET /dashboard/upcoming`` 列表项
- ``RecentFailureItem``      ``GET /dashboard/recent-failures`` 列表项
- ``TimelineBucket``         ``GET /dashboard/timeline`` 列表项
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ============================================================
# Overview 子结构
# ============================================================
class OverviewScripts(BaseModel):
    total: int = Field(..., ge=0)
    enabled: int = Field(..., ge=0)


class OverviewInstances(BaseModel):
    total: int = Field(..., ge=0)
    enabled: int = Field(..., ge=0)
    paused: int = Field(..., ge=0)


class OverviewRuns24h(BaseModel):
    total: int = Field(..., ge=0)
    success: int = Field(..., ge=0)
    failure: int = Field(..., ge=0)
    running: int = Field(..., ge=0)


# ============================================================
# Overview 总响应
# ============================================================
class DashboardOverview(BaseModel):
    """``GET /dashboard/overview`` 响应。"""

    scripts: OverviewScripts
    instances: OverviewInstances
    runs_24h: OverviewRuns24h
    success_rate_24h: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="近 24h 成功率(0.0 - 1.0);无 run 时返回 0.0",
    )
    success_rate_7d: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="近 7 天成功率(0.0 - 1.0);无 run 时返回 0.0",
    )
    sparkline_7d_success: list[float] = Field(
        ...,
        min_length=7,
        max_length=7,
        description="过去 7 天每日成功率(0.0-1.0),长度恒为 7,最后一项是今天;当日无 run 时为 0.0",
    )
    sparkline_7d_runs: list[int] = Field(
        ...,
        min_length=7,
        max_length=7,
        description="过去 7 天每日 run 总数,长度恒为 7,最后一项是今天",
    )
    notifications_24h: int = Field(
        ...,
        ge=0,
        description="过去 24 小时发送过的通知规则数(按 last_fired_at 统计)",
    )
    next_run_at: datetime | None = Field(
        None,
        description="所有 enabled instance 中最早的 next_run_at;无则为 null",
    )


# ============================================================
# 即将执行 / 最近失败
# ============================================================
class UpcomingItem(BaseModel):
    """``GET /dashboard/upcoming`` 列表项。"""

    model_config = ConfigDict(from_attributes=True)

    instance_id: int
    instance_name: str
    script_slug: str
    script_name: str | None = None
    cron_expr: str | None = None
    next_run_at: datetime


class RecentFailureItem(BaseModel):
    """``GET /dashboard/recent-failures`` 列表项。

    包含 ``run_id`` 便于前端跳详情。
    """

    model_config = ConfigDict(from_attributes=True)

    run_id: int
    instance_id: int
    instance_name: str
    script_slug: str
    script_name: str | None = None
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    duration_ms: int | None = None
    result_message: str | None = None


# ============================================================
# Timeline
# ============================================================
class TimelineBucket(BaseModel):
    """``GET /dashboard/timeline`` 单个时间桶。

    ``ts`` 是桶起点(UTC);bucket=hour 时 ts 取小时整点,bucket=day 时取日 0 点。
    """

    ts: datetime
    success: int = Field(..., ge=0)
    failure: int = Field(..., ge=0)
    error: int = Field(..., ge=0)
    timeout: int = Field(..., ge=0)
