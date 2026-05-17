"""执行历史 API — `/api/v1/runs/*`。

实现见 `进度/设计/后端架构.md` § 2.4 + § 2.4.1。

端点清单(5 个)
---------------
- ``GET    /runs``                       🔒 列表,不含 stdout/stderr
- ``DELETE /runs/cleanup``               🔒 ``{ before: ISO8601 }`` 或 ``{ keep_days: N }``
- ``GET    /runs/{id}``                  🔒 详情,完整 stdout/stderr
- ``POST   /runs/{id}/cancel``           🔒 仅 pending/running 可取消
- ``GET    /runs/{id}/logs/stream``      🔒 SSE 实时日志(见 § 2.4.1)

路由声明顺序注意:`/cleanup` 必须放在 `/{id}` 之前,否则被路由当成 id。
"""
from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request, status
from loguru import logger
from sse_starlette.sse import EventSourceResponse

from app.deps import CurrentUser, DBSession, Pagination
from app.schemas.run import (
    RunCleanupRequest,
    RunCleanupResponse,
    RunDetail,
    RunListItem,
    RunListResponse,
)
from app.services import run_service

router = APIRouter(prefix="/runs", tags=["runs"])


# ============================================================
# 内部辅助
# ============================================================
def _run_to_detail(run: Any) -> RunDetail:
    """ORM Run → RunDetail Pydantic;反序列化 result_data_json。"""
    result_data: dict[str, Any] | None = None
    raw = run.result_data_json
    if raw:
        try:
            decoded = json.loads(raw)
            if isinstance(decoded, dict):
                result_data = decoded
            else:
                # 不是 dict 时塞到 "value" 键里(防御性)
                result_data = {"value": decoded}
        except json.JSONDecodeError as exc:  # pragma: no cover
            logger.warning(
                "result_data_json 解析失败 run_id={} err={}", run.id, exc
            )

    return RunDetail(
        id=run.id,
        instance_id=run.instance_id,
        script_slug=run.script_slug,
        trigger_type=run.trigger_type,
        trigger_user_id=run.trigger_user_id,
        parent_run_id=run.parent_run_id,
        status=run.status,
        exit_code=run.exit_code,
        result_message=run.result_message,
        result_data=result_data,
        stdout=run.stdout,
        stderr=run.stderr,
        stdout_truncated=bool(run.stdout_truncated),
        stderr_truncated=bool(run.stderr_truncated),
        started_at=run.started_at,
        finished_at=run.finished_at,
        duration_ms=run.duration_ms,
        host=run.host,
        created_at=run.created_at,
    )


# ============================================================
# 列表
# ============================================================
@router.get(
    "",
    response_model=RunListResponse,
    summary="执行历史列表(不含 stdout/stderr)",
)
def list_runs(
    db: DBSession,
    _user: CurrentUser,
    pagination: Pagination,
    instance_id: Annotated[
        int | None,
        Query(description="按实例筛选"),
    ] = None,
    script_slug: Annotated[
        str | None,
        Query(max_length=64, description="按脚本 slug 筛选"),
    ] = None,
    run_status: Annotated[
        str | None,
        Query(
            alias="status",
            max_length=16,
            description="按状态筛选(pending/running/success/failure/error/timeout/cancelled)",
        ),
    ] = None,
    trigger_type: Annotated[
        str | None,
        Query(
            max_length=16,
            description="按触发类型筛选(manual/scheduled/retry/api)",
        ),
    ] = None,
    started_after: Annotated[
        datetime | None,
        Query(description="started_at >= 此时间(ISO 8601)"),
    ] = None,
    started_before: Annotated[
        datetime | None,
        Query(description="started_at < 此时间(ISO 8601)"),
    ] = None,
    order: Annotated[
        str,
        Query(
            description=(
                "按 started_at 排序方向 — 'desc'(默认 / 最新优先)或 'asc'。"
                "audit High #13:之前前端传 order 后端静默忽略,现已正确生效。"
            ),
            pattern="^(asc|desc)$",
        ),
    ] = "desc",
) -> RunListResponse:
    """🔒 返回 ``{ items, total, page, page_size }``。

    默认按 ``started_at DESC`` 排序;传 ``order=asc`` 可切换升序。
    列表项不含 stdout/stderr。
    """
    page, page_size = pagination
    items, total = run_service.list_runs(
        db,
        instance_id=instance_id,
        script_slug=script_slug,
        status=run_status,
        trigger_type=trigger_type,
        started_after=started_after,
        started_before=started_before,
        order=order,
        page=page,
        page_size=page_size,
    )

    return RunListResponse(
        items=[RunListItem.model_validate(r) for r in items],
        total=total,
        page=page,
        page_size=page_size,
    )


# ============================================================
# 清理(必须先于 /{id} 注册)
# ============================================================
@router.delete(
    "/cleanup",
    response_model=RunCleanupResponse,
    status_code=status.HTTP_200_OK,
    summary="清理旧 run(按时间)",
)
def cleanup(
    payload: RunCleanupRequest,
    db: DBSession,
    _user: CurrentUser,
) -> RunCleanupResponse:
    """🔒 删除旧 run,返回删除数。

    请求体二选一:``{ "before": "ISO8601" }`` 或 ``{ "keep_days": N }``。
    活动 run(pending/running)受保护永不删除。
    """
    deleted = run_service.cleanup_runs(
        db,
        before=payload.before,
        keep_days=payload.keep_days,
    )
    db.commit()
    return RunCleanupResponse(deleted=deleted)


# ============================================================
# SSE 实时日志(必须放在 /{id} 之前)
# ============================================================
# 单 run 订阅者上限交给 LogBroker 自身控制(设计稿 § 2.4.1 上限 10)。
# 6A 的 LogBroker 在 subscribe() 时若超出会抛 ResourceLimitError → 由
# error_handler 中间件转 429,正符合设计稿要求。


def _yield_history_lines(text: str | None, *, max_lines: int | None = None) -> list[str]:
    """把多行 stdout/stderr 切片为单行列表(去掉行尾换行)。"""
    if not text:
        return []
    lines = text.splitlines()
    if max_lines is not None and len(lines) > max_lines:
        return lines[-max_lines:]
    return lines


@router.get(
    "/{run_id}/logs/stream",
    summary="SSE 实时日志(stdout / stderr / status / ping / end)",
)
async def logs_stream(
    run_id: int,
    request: Request,
    db: DBSession,
    _user: CurrentUser,
) -> EventSourceResponse:
    """🔒 SSE 实时日志。

    事件序列::

        event: stdout       data: <一行文本>
        event: stderr       data: <一行文本>
        event: status       data: {"status":...,"exit_code":...,"duration_ms":...}
        event: ping         data: <unix_ts>          # 每 15s 一次保活
        event: end          data: <reason>           # 终止;服务端关闭连接

    流程
    ----
    1. 校验 run 存在 → 取座(429)
    2. 回放已落库 stdout/stderr(行级)
    3. 若 run 已终态 → 立即发 status + end 然后断
    4. 订阅 log_broker(若可用)持续转发实时输出
    5. 客户端断开(``request.is_disconnected()``)→ 释放座位

    若 6A 的 log_broker 尚未实现,降级为"只回放 + 终态推送 status",
    给前端一个完整的关闭流程而不是吊着连接。

    响应头:``X-Accel-Buffering: no``(防 nginx 缓冲)。
    """
    # 1) 校验存在
    run = run_service.get_run(db, run_id)
    initial_status = run.status

    # 提前快照 — 在 generator 内 db session 可能已 close,不能再访问 ORM
    history_stdout = _yield_history_lines(run.stdout)
    history_stderr = _yield_history_lines(run.stderr)
    snapshot_status = {
        "status": run.status,
        "exit_code": run.exit_code,
        "duration_ms": run.duration_ms,
    }

    # 3) 尝试拿 6A 的 LogBroker.channel(若已就绪)
    channel = None
    try:
        from app.runner.log_broker import get_log_broker  # noqa: PLC0415

        broker = get_log_broker()
        # 用 get_or_create 拿,这样即便 executor 还没 publish 也能订阅(等推送)
        channel = broker.get_or_create(run_id)
    except ImportError:
        logger.debug("log_broker 模块未就绪,SSE 降级 run_id={}", run_id)
    except Exception as exc:  # noqa: BLE001
        logger.debug("log_broker 取 channel 失败,降级 run_id={} err={}", run_id, exc)

    is_terminal = initial_status in run_service.RUN_STATUS_TERMINAL

    async def event_gen() -> AsyncIterator[dict[str, Any]]:
        # --- 回放历史 stdout/stderr ---
        for line in history_stdout:
            if await request.is_disconnected():
                return
            yield {"event": "stdout", "data": line}
        for line in history_stderr:
            if await request.is_disconnected():
                return
            yield {"event": "stderr", "data": line}

        # --- run 已终态:直接 status + end ---
        if is_terminal:
            yield {"event": "status", "data": json.dumps(snapshot_status)}
            yield {"event": "end", "data": "terminal"}
            return

        # --- 实时阶段 ---
        # 没有 channel → 给一条提示 + end(避免吊死客户端)
        if channel is None:
            yield {
                "event": "status",
                "data": json.dumps(snapshot_status),
            }
            yield {
                "event": "end",
                "data": "broker_unavailable",
            }
            return

        # 订阅 channel,转发实时事件 + 15s ping
        last_ping = time.monotonic()

        async for ev in channel.subscribe():
            if await request.is_disconnected():
                return
            # 6A LogBroker 事件:{event, data};data 可能是 dict(status)或 str(stdout/stderr)
            if isinstance(ev, dict):
                et = ev.get("event") or "stdout"
                payload = ev.get("data")
                if isinstance(payload, (dict, list)):
                    payload = json.dumps(payload)
                yield {
                    "event": str(et),
                    "data": "" if payload is None else str(payload),
                }
                if et == "end":
                    return
            else:  # pragma: no cover
                yield {"event": "stdout", "data": str(ev)}

            # 顺手发 ping(broker 安静期也想保活)
            now = time.monotonic()
            if now - last_ping >= 15.0:
                yield {"event": "ping", "data": str(int(time.time()))}
                last_ping = now

        # channel 流自然结束
        yield {"event": "end", "data": "broker_closed"}

    headers = {
        # 防 nginx 缓冲(caddy 默认正确,但保险起见)
        "X-Accel-Buffering": "no",
        "Cache-Control": "no-cache",
    }
    return EventSourceResponse(
        event_gen(),
        headers=headers,
        ping=15,  # sse-starlette 内置 ping(若上面手动 ping 触发也无害)
    )


# ============================================================
# 详情
# ============================================================
@router.get(
    "/{run_id}",
    response_model=RunDetail,
    summary="执行详情(含完整 stdout/stderr)",
)
def get_run(
    run_id: int,
    db: DBSession,
    _user: CurrentUser,
) -> RunDetail:
    """🔒 返回完整字段;若 stdout/stderr 被截断,``*_truncated=true``。"""
    run = run_service.get_run(db, run_id)
    return _run_to_detail(run)


# ============================================================
# 取消
# ============================================================
@router.post(
    "/{run_id}/cancel",
    response_model=RunDetail,
    status_code=status.HTTP_200_OK,
    summary="取消正在运行的 run",
)
def cancel_run(
    run_id: int,
    request: Request,
    db: DBSession,
    _user: CurrentUser,
) -> RunDetail:
    """🔒 取消 pending/running 的 run。

    取消信号通过 ``request.app.state.scheduler``(若 6A 已挂)下发到 executor;
    若 scheduler 未就绪,只翻 DB 状态保证 API 可用。
    """
    scheduler = getattr(request.app.state, "scheduler", None)
    run = run_service.cancel_run(db, run_id, scheduler)
    db.commit()
    return _run_to_detail(run)
