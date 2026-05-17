"""仪表盘 service — 聚合查询(纯只读)。

实现见 `进度/设计/后端架构.md` § 2.7。

公开函数
--------
- ``get_overview(db) -> dict``                       概览(scripts/instances/runs_24h/success_rate_*)
- ``get_upcoming(db, limit=10) -> list[dict]``       即将执行(按 next_run_at ASC)
- ``get_recent_failures(db, limit=10) -> list[dict]`` 最近失败
- ``get_timeline(db, bucket='hour', days=7) -> list[dict]``  时间分桶统计

实现要点
--------
- 全部用 SQLAlchemy 2.x ``select(...)`` 风格
- ``get_overview`` 用一次"按状态分组 COUNT"减少 SQL 次数
- ``get_timeline`` 用 SQLite ``strftime`` 分桶 — Python 端兜底补齐空桶
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.instance import Instance
from app.db.models.notification import NotificationRule
from app.db.models.run import Run
from app.db.models.script import Script


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ============================================================
# Overview
# ============================================================
def get_overview(db: Session) -> dict[str, Any]:
    """返回概览 dict,可直接用于 :class:`DashboardOverview.model_validate`。"""
    now = _utcnow()
    t24h = now - timedelta(hours=24)
    t7d = now - timedelta(days=7)

    # scripts: total / enabled
    scripts_total = int(
        db.execute(select(func.count()).select_from(Script)).scalar_one()
    )
    scripts_enabled = int(
        db.execute(
            select(func.count()).select_from(Script).where(Script.enabled.is_(True))
        ).scalar_one()
    )

    # instances: total / enabled / paused
    instances_total = int(
        db.execute(select(func.count()).select_from(Instance)).scalar_one()
    )
    instances_enabled = int(
        db.execute(
            select(func.count())
            .select_from(Instance)
            .where(Instance.enabled.is_(True))
        ).scalar_one()
    )
    # paused = paused_until > now(且 enabled,语义:被暂停)
    instances_paused = int(
        db.execute(
            select(func.count())
            .select_from(Instance)
            .where(Instance.paused_until.isnot(None), Instance.paused_until > now)
        ).scalar_one()
    )

    # runs_24h:按 status 分组 COUNT
    runs_by_status_24h_rows = db.execute(
        select(Run.status, func.count(Run.id))
        .where(Run.started_at >= t24h)
        .group_by(Run.status)
    ).all()
    runs_by_status_24h: dict[str, int] = {s: int(c) for s, c in runs_by_status_24h_rows}
    total_24h = sum(runs_by_status_24h.values())
    success_24h = runs_by_status_24h.get("success", 0)
    failure_24h = (
        runs_by_status_24h.get("failure", 0)
        + runs_by_status_24h.get("error", 0)
        + runs_by_status_24h.get("timeout", 0)
    )
    running_24h = runs_by_status_24h.get("running", 0) + runs_by_status_24h.get(
        "pending", 0
    )

    # 成功率:仅看终态(success / failure / error / timeout / cancelled);
    # 未终态的不算分母,避免新触发的 run 把比例拉低
    terminal_24h = total_24h - runs_by_status_24h.get("pending", 0) - runs_by_status_24h.get(
        "running", 0
    )
    success_rate_24h = (success_24h / terminal_24h) if terminal_24h > 0 else 0.0

    # 7d 成功率
    rows_7d = db.execute(
        select(Run.status, func.count(Run.id))
        .where(Run.started_at >= t7d)
        .group_by(Run.status)
    ).all()
    by_status_7d: dict[str, int] = {s: int(c) for s, c in rows_7d}
    success_7d = by_status_7d.get("success", 0)
    terminal_7d = (
        sum(by_status_7d.values())
        - by_status_7d.get("pending", 0)
        - by_status_7d.get("running", 0)
    )
    success_rate_7d = (success_7d / terminal_7d) if terminal_7d > 0 else 0.0

    # ===== 新增 4 字段 =====
    sparkline_success, sparkline_runs = _compute_sparklines_7d(db, now=now)
    notifications_24h = _count_notifications_24h(db, since=t24h)
    next_run_at = _earliest_next_run_at(db)

    return {
        "scripts": {
            "total": scripts_total,
            "enabled": scripts_enabled,
        },
        "instances": {
            "total": instances_total,
            "enabled": instances_enabled,
            "paused": instances_paused,
        },
        "runs_24h": {
            "total": total_24h,
            "success": success_24h,
            "failure": failure_24h,
            "running": running_24h,
        },
        "success_rate_24h": round(success_rate_24h, 4),
        "success_rate_7d": round(success_rate_7d, 4),
        "sparkline_7d_success": sparkline_success,
        "sparkline_7d_runs": sparkline_runs,
        "notifications_24h": notifications_24h,
        "next_run_at": next_run_at,
    }


# ============================================================
# 7 天 sparkline(每日聚合)
# ============================================================
def _compute_sparklines_7d(
    db: Session,
    *,
    now: datetime,
) -> tuple[list[float], list[int]]:
    """返回 ``(sparkline_7d_success, sparkline_7d_runs)``。

    - 长度恒为 7
    - 末位是今天(本地日,按 SQLite ``strftime`` 本地化)
    - 当日无 run 时:success_rate=0.0,runs=0

    实现:
    - 用 SQLite ``strftime('%Y-%m-%d', started_at)`` 按"日"分桶
    - 拉过去 7 天的 (date, status, count) 三元组,Python 端补齐
    - 成功率分母只看终态(success/failure/error/timeout/cancelled),不含 pending/running
    """
    # 用 Python 端的"今天 UTC 日期"作为末位锚点(简洁稳健)
    today = now.date()
    start_day = today - timedelta(days=6)  # 7 天窗口 [today-6, today]
    start_dt = datetime(start_day.year, start_day.month, start_day.day, tzinfo=timezone.utc)

    bucket_expr = func.strftime("%Y-%m-%d", Run.started_at)
    rows = db.execute(
        select(
            bucket_expr.label("day"),
            Run.status,
            func.count(Run.id),
        )
        .where(Run.started_at >= start_dt)
        .group_by(bucket_expr, Run.status)
    ).all()

    # 初始化 7 个空桶 — key 为 'YYYY-MM-DD' 字符串
    days: list[str] = []
    for i in range(7):
        d = start_day + timedelta(days=i)
        days.append(d.isoformat())

    per_day: dict[str, dict[str, int]] = {
        d: {"success": 0, "failure": 0, "error": 0, "timeout": 0, "cancelled": 0,
            "pending": 0, "running": 0}
        for d in days
    }

    for raw_day, status, count in rows:
        key = str(raw_day) if raw_day else ""
        if key not in per_day:
            # SQLite 可能给的是 UTC 日期与上方对齐;不在窗口就跳过
            continue
        if status in per_day[key]:
            per_day[key][status] = int(count)

    sparkline_success: list[float] = []
    sparkline_runs: list[int] = []
    for d in days:
        cell = per_day[d]
        total = sum(cell.values())
        terminal = total - cell["pending"] - cell["running"]
        sr = (cell["success"] / terminal) if terminal > 0 else 0.0
        sparkline_success.append(round(sr, 4))
        sparkline_runs.append(int(total))

    return sparkline_success, sparkline_runs


# ============================================================
# 通知 24h 发送数
# ============================================================
def _count_notifications_24h(db: Session, *, since: datetime) -> int:
    """统计过去 24 小时发送过通知的规则数。

    依据 ``notification_rules.last_fired_at > since``。dispatcher 在成功送达时
    会写 ``last_fired_at``;节流跳过的规则不写,所以这是"实际推送过"的近似值。
    """
    try:
        return int(
            db.execute(
                select(func.count())
                .select_from(NotificationRule)
                .where(NotificationRule.last_fired_at.isnot(None))
                .where(NotificationRule.last_fired_at > since)
            ).scalar_one()
        )
    except Exception:  # 字段缺失/SQL 异常时降级返 0
        return 0


# ============================================================
# 最早 next_run_at
# ============================================================
def _earliest_next_run_at(db: Session) -> datetime | None:
    """所有 ``enabled = true`` 且 ``next_run_at IS NOT NULL`` 实例的最小 next_run_at。"""
    val = db.execute(
        select(func.min(Instance.next_run_at)).where(
            Instance.enabled.is_(True),
            Instance.next_run_at.isnot(None),
        )
    ).scalar_one()
    if val is None:
        return None
    # SQLite 可能返裸 datetime 无 tz;归一到 UTC
    if isinstance(val, datetime) and val.tzinfo is None:
        val = val.replace(tzinfo=timezone.utc)
    return val


# ============================================================
# Upcoming
# ============================================================
def get_upcoming(db: Session, *, limit: int = 10) -> list[dict[str, Any]]:
    """即将执行 — 按 ``next_run_at`` ASC,仅 enabled 实例且 next_run_at 不为空。"""
    if limit <= 0:
        return []

    stmt = (
        select(
            Instance.id,
            Instance.name,
            Instance.cron_expr,
            Instance.next_run_at,
            Script.slug,
            Script.name,
        )
        .join(Script, Script.id == Instance.script_id)
        .where(
            Instance.enabled.is_(True),
            Instance.next_run_at.isnot(None),
        )
        .order_by(Instance.next_run_at.asc())
        .limit(limit)
    )
    rows = db.execute(stmt).all()
    return [
        {
            "instance_id": int(r[0]),
            "instance_name": r[1],
            "cron_expr": r[2],
            "next_run_at": r[3],
            "script_slug": r[4],
            "script_name": r[5],
        }
        for r in rows
    ]


# ============================================================
# Recent failures
# ============================================================
def get_recent_failures(db: Session, *, limit: int = 10) -> list[dict[str, Any]]:
    """最近失败 run — ``status in (failure, error, timeout)``。"""
    if limit <= 0:
        return []

    failure_states = ("failure", "error", "timeout")

    # 用 LEFT OUTER JOIN(instance 删除后仍能拿到 run 失败记录,见 audit Medium #24)
    stmt = (
        select(
            Run.id,
            Run.instance_id,
            Instance.name,
            Run.script_slug,
            Script.name,
            Run.status,
            Run.started_at,
            Run.finished_at,
            Run.duration_ms,
            Run.result_message,
        )
        .outerjoin(Instance, Instance.id == Run.instance_id)
        .outerjoin(Script, Script.slug == Run.script_slug)
        .where(Run.status.in_(failure_states))
        .order_by(Run.started_at.desc(), Run.id.desc())
        .limit(limit)
    )
    rows = db.execute(stmt).all()
    return [
        {
            "run_id": int(r[0]),
            "instance_id": int(r[1]),
            "instance_name": r[2] if r[2] is not None else f"#{int(r[1])}",
            "script_slug": r[3],
            "script_name": r[4] if r[4] is not None else r[3],
            "status": r[5],
            "started_at": r[6],
            "finished_at": r[7],
            "duration_ms": r[8],
            "result_message": r[9],
        }
        for r in rows
    ]


# ============================================================
# Timeline
# ============================================================
BucketType = Literal["hour", "day"]


def get_timeline(
    db: Session,
    *,
    bucket: BucketType = "hour",
    days: int = 7,
) -> list[dict[str, Any]]:
    """按时间分桶聚合 run 状态。

    SQLite 友好实现:用 ``strftime`` 把 started_at 取整到桶起点,
    GROUP BY 该字符串,然后 Python 补齐空桶。

    返回 ``[{ts, success, failure, error, timeout}]``,按 ts 升序。
    """
    if days <= 0 or bucket not in ("hour", "day"):
        return []

    now = _utcnow()
    start_at = now - timedelta(days=days)

    if bucket == "hour":
        fmt = "%Y-%m-%d %H:00:00"
        delta = timedelta(hours=1)
    else:
        fmt = "%Y-%m-%d 00:00:00"
        delta = timedelta(days=1)

    # SQLite 的 strftime 接受 ISO 时间串/julian/now;SQLAlchemy 暴露为 func.strftime
    # 这里只做 SQLite 支持;若以后切换 PostgreSQL 需替换为 date_trunc
    bucket_expr = func.strftime(fmt, Run.started_at)

    rows = db.execute(
        select(
            bucket_expr.label("bucket"),
            Run.status,
            func.count(Run.id),
        )
        .where(
            Run.started_at >= start_at,
            Run.status.in_(("success", "failure", "error", "timeout")),
        )
        .group_by(bucket_expr, Run.status)
        .order_by(bucket_expr.asc())
    ).all()

    # 在 Python 里构造完整桶序列
    buckets: dict[datetime, dict[str, int]] = {}

    # 初始化空桶(从对齐的起点开始)
    if bucket == "hour":
        bucket_start = now.replace(minute=0, second=0, microsecond=0) - timedelta(
            hours=days * 24 - 1
        )
        bucket_count = days * 24
    else:
        bucket_start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(
            days=days - 1
        )
        bucket_count = days

    for i in range(bucket_count):
        ts = bucket_start + delta * i
        buckets[ts] = {"success": 0, "failure": 0, "error": 0, "timeout": 0}

    # 把查询结果填入对应桶
    for raw_bucket, status, count in rows:
        try:
            ts = datetime.strptime(str(raw_bucket), "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=timezone.utc
            )
        except (ValueError, TypeError):  # pragma: no cover
            continue
        cell = buckets.get(ts)
        if cell is None:
            # 桶外(说明初始化范围不够大,补一个)
            buckets[ts] = {"success": 0, "failure": 0, "error": 0, "timeout": 0}
            cell = buckets[ts]
        if status in cell:
            cell[status] = int(count)

    result = [
        {"ts": ts, **buckets[ts]}
        for ts in sorted(buckets.keys())
    ]
    return result
