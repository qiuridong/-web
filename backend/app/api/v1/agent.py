"""Agent 端 API — `/api/v1/agent/*`(MVP-1 远程 agent)。

设计稿:`进度/设计/远程VPS脚本执行调研.md` § 5 / § 9。

端点清单(4 个)
---------------
- GET  /agent/poll?wait=30           agent 长轮询拉任务
- POST /agent/runs/{run_id}/stdout    agent 增量回传 stdout/stderr
- POST /agent/runs/{run_id}/result    agent 回传终态
- POST /agent/heartbeat               agent 心跳(每 30s)

鉴权:走 ``app.middleware.agent_auth.AgentNode`` 依赖(Bearer token);
**不走** session middleware。CSRF middleware 已豁免 ``/api/v1/agent/*``。

并发与租约
----------
v1 简化:不做"任务 lease + 超时回收"。假设:
- agent 始终在线;若 agent 拉走 task 后崩,run 永远 stuck running(用户 UI 手动 cancel)
- MVP-2 加 lease + 超时 / 重派
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Query, status
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.crypto import get_cipher
from app.core.exceptions import RunNotFound, ValidationError
from app.db.models.instance import Instance
from app.db.models.run import Run
from app.db.models.script import Script
from app.db.session import SessionLocal
from app.deps import DBSession
from app.middleware.agent_auth import AgentNode
from app.runner.log_broker import get_log_broker
from app.schemas.node import (
    AgentHeartbeatRequest,
    AgentHeartbeatResponse,
    AgentPollResponse,
    AgentResultRequest,
    AgentStdoutRequest,
    AgentTaskPayload,
)
from app.scheduler.executor import _extract_env_passthrough
from app.services import node_service

router = APIRouter(prefix="/agent", tags=["agent"])


# ============================================================
# 常量
# ============================================================
#: long polling 单次 wait 最大允许值
POLL_WAIT_MAX = 60

#: long polling 单次 wait 默认值
POLL_WAIT_DEFAULT = 30

#: poll 内部轮询间隔
POLL_TICK_SEC = 1.0


# ============================================================
# 辅助
# ============================================================
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _pluck_pending_task(db: Session, node_slug: str) -> Run | None:
    """查找一条分配给此节点的 pending run,如果有就 reserve(翻 running)并返回。

    并发安全:SQLite + flush 已保证同进程内一次只翻一行(MemoryJobStore + 单 uvicorn worker)。
    """
    host_marker = f"node:{node_slug}"[:64]
    run = db.scalars(
        select(Run)
        .where(Run.status == "pending", Run.host == host_marker)
        .order_by(Run.id)
        .limit(1)
    ).first()
    return run


def _build_task_payload(db: Session, run: Run) -> AgentTaskPayload | None:
    """组装 agent 拿走的 task 数据 — 含解密 config / env_passthrough / script meta。

    返回 None 表示 instance / script 已不存在(agent 端跑不了,run 应该作废)。
    """
    instance = db.get(Instance, run.instance_id)
    if instance is None:
        return None
    script = db.get(Script, instance.script_id)
    if script is None:
        return None

    # 解密 config — 主面板单点负责加解密,下发明文给 agent
    cipher = get_cipher()
    try:
        if instance.config_blob:
            config = cipher.decrypt_dict(instance.config_blob)
        else:
            config = {}
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "agent.poll: 解密 config 失败 instance={} err={}",
            instance.id,
            exc,
        )
        config = {}

    env_passthrough = _extract_env_passthrough(script)

    return AgentTaskPayload(
        run_id=run.id,
        instance_id=instance.id,
        instance_name=instance.name,
        script_slug=script.slug,
        script_version=script.version,
        timeout_sec=instance.timeout_sec or script.default_timeout_sec,
        trigger_type=run.trigger_type,
        attempt=1,  # MVP-1 不支持 retry attempt 传递
        config=config,
        env_passthrough=env_passthrough,
    )


def _append_stream(text: str | None, lines: list[str]) -> str:
    """把新 lines 追加到现有 stdout/stderr 文本(末尾,带换行)。"""
    chunk = "\n".join(lines)
    if not text:
        return chunk
    if not chunk:
        return text
    return text + "\n" + chunk


# ============================================================
# poll — long polling 拉任务
# ============================================================
@router.get(
    "/poll",
    response_model=AgentPollResponse,
    summary="Long polling 拉任务",
)
async def agent_poll(
    node: AgentNode,
    wait: int = Query(
        default=POLL_WAIT_DEFAULT,
        ge=0,
        le=POLL_WAIT_MAX,
        description=f"最长等待秒数 (0..{POLL_WAIT_MAX})",
    ),
) -> AgentPollResponse:
    """agent long polling 拉取任务。

    - 立即查一次有无 pending(分配给本节点);有就返回
    - 没有 → 每 ``POLL_TICK_SEC`` 秒重查一次,直到 ``wait`` 秒
    - 仍无 → 返回 ``{"task": null}``

    任务被拉走时:
    - run.status: pending → running
    - run.started_at: 重置为现在(agent 真正开始跑的时间)
    """
    deadline = _utcnow().timestamp() + wait

    while True:
        with SessionLocal() as db:
            run = _pluck_pending_task(db, node.slug)
            if run is not None:
                # reserve — 翻 running
                payload = _build_task_payload(db, run)
                if payload is None:
                    # instance/script 不在了 — 标 error 并继续找下一条
                    run.status = "error"
                    run.result_message = "instance 或 script 已删除"
                    run.finished_at = _utcnow()
                    run.duration_ms = 0
                    db.commit()
                    continue
                run.status = "running"
                run.started_at = _utcnow()
                db.commit()
                logger.info(
                    "agent.poll: node {!r} 拉走 run {} (instance {})",
                    node.slug,
                    run.id,
                    run.instance_id,
                )
                return AgentPollResponse(task=payload)

        # 没拉到 — 看是否到 deadline
        if _utcnow().timestamp() >= deadline:
            return AgentPollResponse(task=None)
        # 间隔等
        await asyncio.sleep(POLL_TICK_SEC)


# ============================================================
# stdout — 增量回传
# ============================================================
@router.post(
    "/runs/{run_id}/stdout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Agent 增量回传 stdout/stderr(SSE 透传 + append 落库)",
)
async def agent_stdout(
    run_id: int,
    payload: AgentStdoutRequest,
    node: AgentNode,
    db: DBSession,
) -> None:
    """agent 跑脚本期间每 1-2s POST 一批新行。

    主面板:
    - 立即 ``log_broker.publish(run_id, stream, line)`` → SSE 转发给浏览器订阅者
    - 追加到 ``runs.stdout`` / ``runs.stderr``(主程序断电也不丢)
    """
    # 校验 run 存在且分配给本节点
    run = db.get(Run, run_id)
    if run is None:
        raise RunNotFound(
            f"run {run_id} 不存在", details={"run_id": run_id}
        )
    expected_host = f"node:{node.slug}"[:64]
    if run.host != expected_host:
        raise ValidationError(
            f"该 run 不属于节点 {node.slug!r}",
            details={"run_id": run_id, "run_host": run.host},
        )

    # 1) SSE 实时转发
    broker = get_log_broker()
    for line in payload.lines:
        try:
            broker.publish(run_id, payload.stream, line)
        except Exception as exc:  # noqa: BLE001
            logger.debug("agent.stdout: broker publish 失败 {}", exc)

    # 2) Append 到 DB(限制 256 KiB 上限)
    MAX_BYTES = 262144  # 256 KiB
    if payload.stream == "stdout":
        new_text = _append_stream(run.stdout, payload.lines)
        if len(new_text.encode("utf-8")) > MAX_BYTES:
            new_text = new_text.encode("utf-8")[-MAX_BYTES:].decode(
                "utf-8", errors="replace"
            )
            run.stdout_truncated = True
        run.stdout = new_text
    else:
        new_text = _append_stream(run.stderr, payload.lines)
        if len(new_text.encode("utf-8")) > MAX_BYTES:
            new_text = new_text.encode("utf-8")[-MAX_BYTES:].decode(
                "utf-8", errors="replace"
            )
            run.stderr_truncated = True
        run.stderr = new_text
    db.commit()


# ============================================================
# result — 终态回传
# ============================================================
@router.post(
    "/runs/{run_id}/result",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Agent 回传 run 终态",
)
async def agent_result(
    run_id: int,
    payload: AgentResultRequest,
    node: AgentNode,
    db: DBSession,
) -> None:
    """agent 跑完脚本后回传终态。

    主面板:
    - 写 ``run.status / exit_code / result_message / result_data / stdout / stderr / finished_at``
    - 同步 ``instance.last_run_*`` 冗余字段
    - 关闭 SSE broker channel(end 事件)
    - 触发通知 ``dispatch_run_event``
    """
    run = db.get(Run, run_id)
    if run is None:
        raise RunNotFound(
            f"run {run_id} 不存在", details={"run_id": run_id}
        )
    expected_host = f"node:{node.slug}"[:64]
    if run.host != expected_host:
        raise ValidationError(
            f"该 run 不属于节点 {node.slug!r}",
            details={"run_id": run_id, "run_host": run.host},
        )

    # 已被 cancel?(用户手动 cancel 过)— 保持 cancelled 状态
    already_cancelled = run.status == "cancelled"
    finished_at = _utcnow()

    if not already_cancelled:
        run.status = payload.status
        run.exit_code = payload.exit_code
        run.result_message = (payload.message or "")[:512]
    # 不论 cancel 与否,都把 stdout/stderr 收上来
    if payload.stdout is not None:
        # 用 agent 上报的完整 stdout 覆盖(已经累计过 stdout/stderr 增量也无所谓)
        run.stdout = payload.stdout
        run.stdout_truncated = bool(payload.stdout_truncated)
    if payload.stderr is not None:
        run.stderr = payload.stderr
        run.stderr_truncated = bool(payload.stderr_truncated)
    if not already_cancelled or run.finished_at is None:
        run.finished_at = finished_at
    if not already_cancelled or run.duration_ms is None:
        if payload.duration_ms is not None:
            run.duration_ms = payload.duration_ms
        elif run.started_at is not None:
            started = run.started_at
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            run.duration_ms = int((finished_at - started).total_seconds() * 1000)

    # 写 result_data
    if payload.data:
        try:
            run.result_data_json = json.dumps(
                payload.data, ensure_ascii=False, separators=(",", ":")
            )
        except (TypeError, ValueError):
            run.result_data_json = json.dumps(
                {"_unserializable": True}, ensure_ascii=False
            )

    db.flush()

    # 同步 instance 冗余字段
    instance = db.get(Instance, run.instance_id)
    if instance is not None:
        instance.last_run_id = run.id
        instance.last_run_status = run.status
        instance.last_run_at = run.finished_at or run.started_at
        instance.total_runs = (instance.total_runs or 0) + 1
        if run.status == "success":
            instance.total_successes = (instance.total_successes or 0) + 1

    db.commit()

    # SSE 广播终态 + 关 broker
    broker = get_log_broker()
    try:
        broker.publish_status(
            run_id,
            {
                "status": run.status,
                "exit_code": run.exit_code,
                "duration_ms": run.duration_ms,
                "result_message": run.result_message,
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("agent.result: publish_status 失败 {}", exc)
    finally:
        try:
            broker.close(run_id)
        except Exception:  # noqa: BLE001
            pass

    # 触发通知(safe wrapped — 不影响 agent 路径)
    try:
        from app.scheduler.executor import _dispatch_notification  # noqa: PLC0415

        await _dispatch_notification(run_id, run.status)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "agent.result: dispatch_notification 失败 run={} {}",
            run_id,
            exc,
        )

    logger.info(
        "agent.result: node {!r} run {} → {} ({})",
        node.slug,
        run_id,
        run.status,
        run.result_message,
    )


# ============================================================
# heartbeat — agent 心跳
# ============================================================
@router.post(
    "/heartbeat",
    response_model=AgentHeartbeatResponse,
    summary="Agent 心跳(每 30s 一次,带 version + metadata)",
)
async def agent_heartbeat(
    payload: AgentHeartbeatRequest,
    node: AgentNode,
    db: DBSession,
) -> AgentHeartbeatResponse:
    """agent 心跳。

    - middleware 已经在 ``authenticate_agent`` 内更新 ``last_seen_at``,这里只是
      再次刷新 + 顺便存 ``version / metadata``
    """
    node_service.update_heartbeat(
        db,
        node.id,
        version=payload.version,
        metadata=payload.metadata,
    )
    db.commit()
    return AgentHeartbeatResponse(
        ok=True,
        server_time=_utcnow(),
        node_id=node.id,
        node_slug=node.slug,
    )
