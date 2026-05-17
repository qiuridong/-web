"""仪表盘聚合 API — `/api/v1/dashboard/*`。

实现见 `进度/设计/后端架构.md` § 2.7。

端点清单(4 个)
----------------
- ``GET /dashboard/overview``          🔒 KPI 一站式聚合
- ``GET /dashboard/upcoming``          🔒 ``?limit=10``
- ``GET /dashboard/recent-failures``   🔒 ``?limit=10``
- ``GET /dashboard/timeline``          🔒 ``?bucket=hour|day&days=7``
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.deps import CurrentUser, DBSession
from app.schemas.dashboard import (
    DashboardOverview,
    RecentFailureItem,
    TimelineBucket,
    UpcomingItem,
)
from app.services import dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# ============================================================
# Overview
# ============================================================
@router.get(
    "/overview",
    response_model=DashboardOverview,
    summary="一站式 KPI 聚合",
)
def overview(
    db: DBSession,
    _user: CurrentUser,
) -> DashboardOverview:
    """🔒 返回 scripts / instances / runs_24h / success_rate_24h / success_rate_7d。"""
    data = dashboard_service.get_overview(db)
    return DashboardOverview.model_validate(data)


# ============================================================
# Upcoming
# ============================================================
@router.get(
    "/upcoming",
    response_model=list[UpcomingItem],
    summary="即将执行的实例(按 next_run_at ASC)",
)
def upcoming(
    db: DBSession,
    _user: CurrentUser,
    limit: Annotated[
        int,
        Query(ge=1, le=100, description="返回条数,默认 10"),
    ] = 10,
) -> list[UpcomingItem]:
    """🔒 仅 enabled 实例且 next_run_at 不为空。"""
    rows = dashboard_service.get_upcoming(db, limit=limit)
    return [UpcomingItem.model_validate(r) for r in rows]


# ============================================================
# Recent failures
# ============================================================
@router.get(
    "/recent-failures",
    response_model=list[RecentFailureItem],
    summary="最近失败的 run",
)
def recent_failures(
    db: DBSession,
    _user: CurrentUser,
    limit: Annotated[
        int,
        Query(ge=1, le=100, description="返回条数,默认 10"),
    ] = 10,
) -> list[RecentFailureItem]:
    """🔒 status in (failure, error, timeout),按 started_at DESC。"""
    rows = dashboard_service.get_recent_failures(db, limit=limit)
    return [RecentFailureItem.model_validate(r) for r in rows]


# ============================================================
# Timeline
# ============================================================
@router.get(
    "/timeline",
    response_model=list[TimelineBucket],
    summary="时间分桶统计 — 前端画堆叠图",
)
def timeline(
    db: DBSession,
    _user: CurrentUser,
    bucket: Annotated[
        str,
        Query(
            description="hour | day",
            pattern="^(hour|day)$",
        ),
    ] = "hour",
    days: Annotated[
        int,
        Query(ge=1, le=90, description="回溯天数,默认 7"),
    ] = 7,
) -> list[TimelineBucket]:
    """🔒 返回 [{ts, success, failure, error, timeout}] 升序。"""
    rows = dashboard_service.get_timeline(db, bucket=bucket, days=days)  # type: ignore[arg-type]
    return [TimelineBucket.model_validate(r) for r in rows]
