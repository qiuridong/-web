"""任务执行流程编排 — § 4.4 完整 14 步。

实现见 `进度/设计/后端架构.md` § 4.4 / § 4.5 / § 3.4 / § 5.5。

入口
----
:func:`execute_run(scheduler, instance_id, *, trigger_type, parent_run_id, trigger_user_id)`
异步入口,负责完整流程,可被:
- API ``POST /instances/{id}/run`` 直接 ``asyncio.create_task(...)`` 调
- APScheduler cron job 触发函数
- retry 一次性 job

:func:`run_instance_test(...)` 试运行版,不写 ``runs`` 表、不发通知,
返回 dict 给 ``POST /instances/{id}/test`` 用。

设计稿要求
----------
- 并发槽位 :class:`ConcurrencyLimiter` 控制(§ 4.4 [1])
- 子进程超时强杀(§ 4.4 [9] + § 3.4):SIGTERM → 5s → SIGKILL
- Windows 容错:用 ``CREATE_NEW_PROCESS_GROUP`` 替代 ``start_new_session``
- ``cwd`` = ``scripts/<slug>/`` 绝对路径,``env`` 走白名单
- 实时 stdout/stderr 推 :class:`LogBroker` 让 SSE 拿到
- 失败重试按指数退避(§ 4.5)
"""
from __future__ import annotations

import asyncio
import os
import signal
import sys
import time
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.crypto import get_cipher
from app.db.models.instance import Instance
from app.db.models.run import Run
from app.db.models.script import Script
from app.db.session import SessionLocal
from app.plugins.fields import validate_config
from app.plugins.manifest import ManifestField
from app.runner.log_broker import get_log_broker
from app.runner.stdio_protocol import (
    RunContextPayload,
    pack_input,
    parse_result_line,
)
from app.scheduler.concurrency import get_limiter
from app.scheduler.retry import compute_retry_delay, should_retry

if TYPE_CHECKING:
    from app.scheduler.engine import SchedulerService

# ============================================================
# 常量
# ============================================================
#: 子进程超时后给 SIGTERM 后等待多久再升级 SIGKILL
KILL_GRACE_SEC: int = 5

#: stdout/stderr 各自落库上限(字节);超出尾部截断
DEFAULT_MAX_LOG_BYTES: int = 262144  # 256 KiB

#: result_data_json 上限
RESULT_DATA_MAX: int = 16384  # 16 KiB

#: 主程序定位 — backend/ 绝对路径(audit Critical #1 后,不再用作 PYTHONPATH)
_BACKEND_DIR: Path = Path(__file__).resolve().parents[2]


# ============================================================
# 活跃子进程注册表(audit Critical #2)
# ============================================================
#: 记录 run_id → asyncio.subprocess.Process 的活跃子进程
#: 设计稿 § 2.4:``cancel_run`` 需要拿到 proc 才能 SIGTERM/SIGKILL
#: 而 run_service.cancel_run 又需要通过 scheduler.cancel_run(run_id) 转发到这里
_ACTIVE_PROCESSES: dict[int, asyncio.subprocess.Process] = {}


def register_active_process(
    run_id: int, proc: asyncio.subprocess.Process
) -> None:
    """注册一个活跃子进程,供 ``cancel_run`` 找到。

    由 executor 在 ``proc`` 启动成功后调用。
    """
    if run_id and run_id > 0:
        _ACTIVE_PROCESSES[run_id] = proc


def unregister_active_process(run_id: int) -> None:
    """从注册表移除。

    由 executor 在子进程退出后调用(无论正常退出 / 超时 / 异常)。
    """
    if run_id and run_id > 0:
        _ACTIVE_PROCESSES.pop(run_id, None)


def get_active_process(run_id: int) -> asyncio.subprocess.Process | None:
    """供测试 / scheduler 查活跃子进程。"""
    return _ACTIVE_PROCESSES.get(run_id)


async def terminate_active_process(run_id: int) -> bool:
    """对 run_id 对应的活跃子进程发取消信号(SIGTERM → 5s → SIGKILL)。

    audit Critical #2:这是 ``scheduler.cancel_run`` → 真杀子进程的核心入口。

    :returns: True 若有活跃进程且已对其发信号;False 若未找到(可能已自然退出)
    """
    proc = _ACTIVE_PROCESSES.get(run_id)
    if proc is None:
        return False
    if proc.returncode is not None:
        # 进程已退出 — 清理 registry
        _ACTIVE_PROCESSES.pop(run_id, None)
        return False
    try:
        await _terminate_subprocess(proc)
    finally:
        # 终止后从 registry 移除(也防 executor 没机会自己清)
        _ACTIVE_PROCESSES.pop(run_id, None)
    return True


# ============================================================
# 工具
# ============================================================
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _truncate(buf: bytes, limit: int) -> tuple[str, bool]:
    """字节 buffer 解码为 utf-8 字符串,超 limit 尾部截断。

    返回 ``(text, was_truncated)``。
    """
    if len(buf) <= limit:
        return buf.decode("utf-8", errors="replace"), False
    # 截尾部 limit 字节,前面加省略提示
    tail = buf[-limit:]
    # 加个 prefix 提示
    head = b"[...truncated...]\n"
    return (head + tail).decode("utf-8", errors="replace"), True


def _build_env(
    *,
    instance_id: int,
    run_id: int,
    script_slug: str,
    data_dir: str,
    env_passthrough: Iterable[str],
) -> dict[str, str]:
    """构造子进程的最小白名单 env(设计稿 § 5.5)。

    **audit Critical #1**:不再透传 ``PYTHONPATH``,不再让子进程能 ``import app.*``。
    子进程通过独立的 ``backend/sandbox_runner.py`` 启动(见 ``_run_subprocess`` 的
    ``cmd`` 组装),该文件**不在 ``app/`` 树下**且自行调 ``_isolate_sys_path`` 把
    backend/ 从 sys.path 移除,从根上断了脚本读 Fernet 主密钥的路径。

    必给:PATH / HOME / LANG / PYTHONUNBUFFERED / PYTHONIOENCODING
        + RUN_ID / INSTANCE_ID / SCRIPT_SLUG / DATA_DIR
    可选透传:``runtime.env_passthrough`` 中声明的变量(典型 HTTP_PROXY 等)

    **严禁透传**:``ENCRYPTION_KEY_PATH`` / ``DATABASE_URL`` / ``PYTHONPATH``
    (audit Critical #1 修复后 PYTHONPATH 已彻底不传)
    """
    env: dict[str, str] = {}
    # 必给
    if sys.platform == "win32":
        # Windows 上 PATH/SystemRoot 缺失会让子进程几乎啥都做不了
        for k in ("PATH", "SYSTEMROOT", "SystemRoot", "COMSPEC", "TEMP", "TMP"):
            if k in os.environ:
                env[k] = os.environ[k]
        env.setdefault("HOME", os.environ.get("USERPROFILE", ""))
    else:
        if "PATH" in os.environ:
            env["PATH"] = os.environ["PATH"]
        env.setdefault("HOME", os.environ.get("HOME", "/tmp"))
    env["LANG"] = os.environ.get("LANG", "C.UTF-8")
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    # 业务
    env["RUN_ID"] = str(run_id)
    env["INSTANCE_ID"] = str(instance_id)
    env["SCRIPT_SLUG"] = script_slug
    env["DATA_DIR"] = data_dir

    # ============================================================
    # PYTHONPATH 安全透传(2026-05-18 hotfix,fix MVP-4 audit Critical #1 过头修复)
    # ------------------------------------------------------------
    # 历史:audit Critical #1(2026-05-16)修复时一刀切禁止 PYTHONPATH 透传,
    #       假设第三方依赖在 backend/.venv/Lib/site-packages(本机开发模式 OK)。
    # 真相:生产 Docker 走 `uv pip install --target /deps` + `ENV PYTHONPATH=/deps`,
    #       第三方包(httpx 等)在 /deps,不在 site-packages。子进程没继承
    #       PYTHONPATH → import httpx 失败 → 所有用 httpx 的脚本(coklw/ptfans)
    #       scheduled 触发 100% 失败("脚本加载失败 ModuleNotFoundError")。
    # 修复:**白名单透传** PYTHONPATH —— 过滤掉指向 backend/ 的路径
    #       (防 import app.*),保留 /deps 等纯第三方依赖路径。
    # 安全性:与 audit Critical #1 目标对齐 —— 子进程仍然不能 import app.*
    #       (因 backend/ 路径会被过滤;sandbox_runner._isolate_sys_path 也兜底)。
    # ============================================================
    parent_pythonpath = os.environ.get("PYTHONPATH", "")
    if parent_pythonpath:
        safe_paths: list[str] = []
        for p in parent_pythonpath.split(os.pathsep):
            if not p:
                continue
            try:
                abs_p = Path(p).resolve()
            except (OSError, ValueError):
                continue
            # 拒绝 backend/ 本身(防 import app)
            if abs_p == _BACKEND_DIR:
                continue
            # 拒绝 backend/ 任何子路径(兜底,防有人把 backend/app 加 PYTHONPATH)
            try:
                if abs_p.is_relative_to(_BACKEND_DIR):
                    continue
            except (ValueError, AttributeError):
                # is_relative_to 3.9+;older fallback
                if str(abs_p).startswith(str(_BACKEND_DIR) + os.sep):
                    continue
            safe_paths.append(p)  # 原样保留(不是 abs_p 字符串,保持原路径形态)
        if safe_paths:
            env["PYTHONPATH"] = os.pathsep.join(safe_paths)

    # 透传白名单(过滤敏感项 — 防 env_passthrough 配错)
    # PYTHONPATH 已经在上面安全透传,这里若 env_passthrough 又含 PYTHONPATH
    # 也要拒绝(避免脚本作者覆盖)
    _FORBIDDEN = {
        "PYTHONPATH",
        "ENCRYPTION_KEY",
        "ENCRYPTION_KEY_PATH",
        "DATABASE_URL",
        "SECRET_KEY",
    }
    for name in env_passthrough or []:
        if name in _FORBIDDEN:
            logger.warning(
                "env_passthrough 含敏感变量 {!r},已强制拒绝(audit Critical #1)",
                name,
            )
            continue
        if name in os.environ:
            env[name] = os.environ[name]

    return env


def _spawn_kwargs() -> dict[str, Any]:
    """返回 asyncio.create_subprocess_exec 的平台相关 kwargs。

    Linux:``start_new_session=True`` 让子进程独立 process group
    Windows:``creationflags=CREATE_NEW_PROCESS_GROUP``
    """
    if sys.platform == "win32":
        import subprocess as _sp  # 仅本函数内用
        return {"creationflags": _sp.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


async def _terminate_subprocess(proc: asyncio.subprocess.Process) -> None:
    """对子进程发送终止信号,grace 后强杀。

    Linux:对进程组发 SIGTERM → 5s → SIGKILL
    Windows:发 CTRL_BREAK_EVENT → 5s → ``proc.kill()``
    """
    if proc.returncode is not None:
        return
    try:
        if sys.platform == "win32":
            try:
                proc.send_signal(signal.CTRL_BREAK_EVENT)
            except (ValueError, OSError):
                proc.terminate()
        else:
            pgid = os.getpgid(proc.pid)
            os.killpg(pgid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return

    try:
        await asyncio.wait_for(proc.wait(), timeout=KILL_GRACE_SEC)
        return
    except asyncio.TimeoutError:
        pass

    # grace 过了还活着 → 强杀
    try:
        if sys.platform == "win32":
            proc.kill()
        else:
            pgid = os.getpgid(proc.pid)
            os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        return
    try:
        await asyncio.wait_for(proc.wait(), timeout=5)
    except asyncio.TimeoutError:  # pragma: no cover — 极端情况
        logger.error(f"子进程 SIGKILL 后仍未退出 pid={proc.pid}")


# ============================================================
# 解析 fields_schema_json → ManifestField 列表
# ============================================================
def _load_fields(script: Script) -> list[ManifestField]:
    """从 ``script.fields_schema_json`` 反序列化为 ManifestField 列表。

    用于 ``validate_config`` 二次校验 + ``mask_secrets``。
    """
    import json as _json

    raw = _json.loads(script.fields_schema_json or "[]")
    if not isinstance(raw, list):
        raise ValueError("fields_schema_json 顶层必须是数组")
    return [ManifestField.model_validate(item) for item in raw]


# ============================================================
# 子流程执行 — 与 DB 解耦,纯执行
# ============================================================
async def _run_subprocess(
    *,
    script_dir: Path,
    config: dict[str, Any],
    context: RunContextPayload,
    timeout_sec: int,
    env_passthrough: Iterable[str],
    broker_publish: Any | None = None,
    max_log_bytes: int = DEFAULT_MAX_LOG_BYTES,
) -> dict[str, Any]:
    """启动 sandbox 子进程并捕获 stdout/stderr/RunResult。

    :returns: dict 含
        - ``status``: success / failure / error / timeout
        - ``exit_code``: int | None
        - ``duration_ms``: int
        - ``result_message``: str
        - ``result_data``: dict
        - ``stdout``: str
        - ``stderr``: str
        - ``stdout_truncated``: bool
        - ``stderr_truncated``: bool
    """
    env = _build_env(
        instance_id=context.instance_id,
        run_id=context.run_id,
        script_slug=context.script_slug,
        data_dir=context.data_dir,
        env_passthrough=env_passthrough,
    )

    # audit Critical #1:用独立的 backend/sandbox_runner.py 启动 — **不**通过
    # ``-m app.runner.sandbox``,因为后者要求 ``app/`` 可被 import,会逼我们传
    # PYTHONPATH=backend/,等价于让脚本能 ``import app.core.crypto`` 拿密钥。
    # sandbox_runner.py 是独立模块,启动后自己调 ``_isolate_sys_path`` 清 backend/
    # 路径,从根上断了脚本读密钥的路径。
    _sandbox_path = _BACKEND_DIR / "sandbox_runner.py"
    cmd = [sys.executable, "-u", str(_sandbox_path)]

    start_ts = time.monotonic()
    started_at = _utcnow()

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(script_dir),
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **_spawn_kwargs(),
        )
    except (OSError, FileNotFoundError) as exc:
        return {
            "status": "error",
            "exit_code": None,
            "duration_ms": int((time.monotonic() - start_ts) * 1000),
            "result_message": f"子进程启动失败: {type(exc).__name__}: {exc}",
            "result_data": {},
            "stdout": "",
            "stderr": f"[exec failed] {exc}",
            "stdout_truncated": False,
            "stderr_truncated": False,
            "started_at": started_at,
            "finished_at": _utcnow(),
        }

    # audit Critical #2:注册到活跃 process registry,供 cancel_run 找到
    register_active_process(context.run_id, proc)

    # 写 stdin 然后关闭
    stdin_payload = pack_input(config=config, context=context)
    try:
        assert proc.stdin is not None
        proc.stdin.write(stdin_payload.encode("utf-8"))
        await proc.stdin.drain()
        proc.stdin.close()
    except (BrokenPipeError, ConnectionResetError):
        # 子进程已退出,继续按收尾流程处理
        pass

    # 收集 stdout/stderr — 按行流式读,推 broker + 累积 buffer(截断)
    stdout_buf = bytearray()
    stderr_buf = bytearray()
    stdout_truncated = False
    stderr_truncated = False

    async def _pump(
        reader: asyncio.StreamReader | None,
        sink: bytearray,
        stream_name: str,
    ) -> None:
        nonlocal stdout_truncated, stderr_truncated
        if reader is None:
            return
        while True:
            try:
                # 读一行(尝试限制最大行长避免畸形输出炸内存)
                line = await reader.readline()
            except (asyncio.LimitOverrunError, ValueError):
                # 太长的"一行" — 退化读固定字节
                line = await reader.read(65536)
            if not line:
                return

            # 累积(带截断)
            limit = max_log_bytes
            current = sink
            if len(current) + len(line) <= limit:
                current.extend(line)
            else:
                # 还没超 → 部分追加;之后丢弃
                remaining = max(0, limit - len(current))
                if remaining:
                    current.extend(line[:remaining])
                if stream_name == "stdout":
                    stdout_truncated = True
                else:
                    stderr_truncated = True

            # 实时 broker:解码行后推
            if broker_publish is not None:
                try:
                    text = line.decode("utf-8", errors="replace").rstrip()
                    if text:
                        broker_publish(stream_name, text)
                except Exception:  # noqa: BLE001
                    pass

    pumps = [
        asyncio.create_task(_pump(proc.stdout, stdout_buf, "stdout")),
        asyncio.create_task(_pump(proc.stderr, stderr_buf, "stderr")),
    ]

    # 等子进程或超时
    timed_out = False
    try:
        async with asyncio.timeout(timeout_sec):  # Python 3.11+
            await proc.wait()
    except TimeoutError:
        timed_out = True
        logger.warning(
            "子进程超时 instance_id={} run_id={} timeout={}s pid={}",
            context.instance_id,
            context.run_id,
            timeout_sec,
            proc.pid,
        )
        # 写一条 stderr 通知到 broker(也会落 sink)
        marker = f"[TIMEOUT after {timeout_sec}s, killing process tree]\n".encode("utf-8")
        stderr_buf.extend(marker)
        if broker_publish is not None:
            try:
                broker_publish("stderr", marker.decode("utf-8").rstrip())
            except Exception:  # noqa: BLE001
                pass
        await _terminate_subprocess(proc)
    except Exception as exc:  # noqa: BLE001
        # 任何其他异常 — 也尝试清理子进程
        logger.error(
            "executor 异常 instance_id={} run_id={} err={}",
            context.instance_id,
            context.run_id,
            exc,
        )
        await _terminate_subprocess(proc)
        raise
    finally:
        # 等 pump 收尾(子进程已退出,reader 自然 EOF)
        for t in pumps:
            try:
                await asyncio.wait_for(t, timeout=2)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                t.cancel()
        # audit Critical #2:无论正常退出/超时/异常,都从活跃 process registry 移除
        unregister_active_process(context.run_id)

    exit_code = proc.returncode if proc.returncode is not None else -1
    finished_at = _utcnow()
    duration_ms = int((time.monotonic() - start_ts) * 1000)

    # 如果是被外部 cancel 信号杀掉的(SIGTERM/SIGKILL via terminate_active_process),
    # 这里 returncode 可能是负数(信号杀)或正常退出,但 RUN 表已被 cancel_run 翻成
    # ``cancelled``。我们这里返回的结果会被 execute_run 写回 DB 覆盖 → 所以
    # execute_run 在写回前要判断"是否已被外部置为 cancelled"。下面 execute_run 已加
    # 此保护(看那处的注释)。

    # 解析 stdout 最后一行 __RUN_RESULT__
    stdout_text, was_so_trunc = _truncate(bytes(stdout_buf), DEFAULT_MAX_LOG_BYTES)
    stderr_text, was_se_trunc = _truncate(bytes(stderr_buf), DEFAULT_MAX_LOG_BYTES)
    stdout_truncated = stdout_truncated or was_so_trunc
    stderr_truncated = stderr_truncated or was_se_trunc

    result_dict: dict[str, Any] | None = None
    # 从下往上找 result 标记行 — 防止后续 buffer 输出干扰
    for line in reversed(stdout_text.splitlines()):
        parsed = parse_result_line(line)
        if parsed is not None:
            result_dict = parsed
            break

    if timed_out:
        status = "timeout"
        exit_code = -15  # 符合 § 3.3.2 约定
        message = f"脚本超时(>{timeout_sec}s),已强制终止"
        data: dict[str, Any] = {}
    elif result_dict is not None:
        success = bool(result_dict.get("success", False))
        status = "success" if success else "failure"
        message = str(result_dict.get("message", ""))[:512]
        data = result_dict.get("data") or {}
        if not isinstance(data, dict):
            data = {"_raw": str(data)[:RESULT_DATA_MAX]}
    elif exit_code == 0:
        # 退出 0 但无 result 行 → 协议异常
        status = "error"
        message = "子进程退出 0 但未输出 __RUN_RESULT__ 行(协议异常)"
        data = {}
    else:
        status = "error"
        message = f"子进程异常退出 exit_code={exit_code},未拿到 RunResult"
        data = {}

    return {
        "status": status,
        "exit_code": exit_code,
        "duration_ms": duration_ms,
        "result_message": message,
        "result_data": data,
        "stdout": stdout_text,
        "stderr": stderr_text,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "started_at": started_at,
        "finished_at": finished_at,
    }


# ============================================================
# DB 协作 — 真实 run 走这条路径
# ============================================================
async def execute_run(
    scheduler: "SchedulerService | None",
    instance_id: int,
    *,
    trigger_type: str = "manual",
    trigger_user_id: int | None = None,
    parent_run_id: int | None = None,
    attempt: int = 1,
    pre_created_run_id: int | None = None,
) -> int:
    """完整执行流程(§ 4.4 14 步)。返回 ``run_id``。

    :param scheduler: SchedulerService 实例,用于失败重试时调度 retry job;
                       传 None 表示不重试(测试或 SIGTERM 关停场景)
    :param instance_id: 待执行实例
    :param trigger_type: ``manual`` / ``scheduled`` / ``retry`` / ``api``
    :param trigger_user_id: manual 触发时的用户 id
    :param parent_run_id: retry 时指向上次失败 run
    :param attempt: 第几次尝试,首次=1
    :param pre_created_run_id: 若上层已先创建 run 行(例如 API 立即触发要
                                返回 run_id 给前端),传入此 id 复用
    """
    limiter = get_limiter()
    broker = get_log_broker()
    settings = get_settings()

    # ===== [1] 获取并发槽位 =====
    async with limiter.slot():
        # ===== [2-3] 在 DB session 内创建 / 更新 run + 加载 instance/script =====
        # 注意:每个 run 用独立 session,避免与外部请求 session 干扰
        with SessionLocal() as db:
            instance: Instance | None = db.scalars(
                select(Instance).where(Instance.id == instance_id)
            ).one_or_none()
            if instance is None:
                logger.error("executor: instance {} 不存在", instance_id)
                broker.close(pre_created_run_id) if pre_created_run_id else None
                return -1

            script: Script | None = db.scalars(
                select(Script).where(Script.id == instance.script_id)
            ).one_or_none()
            if script is None:
                logger.error(
                    "executor: instance {} 关联 script {} 不存在",
                    instance_id,
                    instance.script_id,
                )
                return -1

            # 状态判断:script / instance 都得 enabled
            if not script.enabled:
                logger.info(
                    "executor: 跳过 — script {} 已禁用",
                    script.slug,
                )
                # 若已预创建 run,标记 cancelled
                if pre_created_run_id is not None:
                    _finalize_skipped_run(
                        db, pre_created_run_id, "script_disabled"
                    )
                    db.commit()
                return pre_created_run_id or -1
            if not instance.enabled and trigger_type == "scheduled":
                logger.info("executor: 跳过 — instance {} 已禁用", instance_id)
                if pre_created_run_id is not None:
                    _finalize_skipped_run(
                        db, pre_created_run_id, "instance_disabled"
                    )
                    db.commit()
                return pre_created_run_id or -1

            # paused_until 检查(仅 scheduled 触发时尊重;manual 强制跑)
            now = _utcnow()
            if (
                trigger_type == "scheduled"
                and instance.paused_until is not None
                and instance.paused_until > now
            ):
                logger.info(
                    "executor: 跳过 — instance {} paused_until={}",
                    instance_id,
                    instance.paused_until,
                )
                if pre_created_run_id is not None:
                    _finalize_skipped_run(db, pre_created_run_id, "paused")
                    db.commit()
                return pre_created_run_id or -1

            # ===== 创建 / 复用 run 行 =====
            if pre_created_run_id is not None:
                run = db.get(Run, pre_created_run_id)
                if run is None:
                    logger.error(
                        "pre_created_run_id={} 找不到,降级新建", pre_created_run_id
                    )
                    pre_created_run_id = None

            if pre_created_run_id is None:
                run = Run(
                    instance_id=instance_id,
                    script_slug=script.slug,
                    trigger_type=trigger_type,
                    trigger_user_id=trigger_user_id,
                    parent_run_id=parent_run_id,
                    status="pending",
                    started_at=now,
                )
                db.add(run)
                db.flush()  # 拿 id

            # 提交 — 让外界尽快看到 run 已创建
            db.commit()
            db.refresh(run)
            run_id = run.id

            # ===== [4] 解密 config_blob + 二次校验 =====
            try:
                if instance.config_blob:
                    config = get_cipher().decrypt_dict(instance.config_blob)
                else:
                    config = {}
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "config 解密失败 instance={}: {}", instance_id, exc
                )
                run.status = "error"
                run.exit_code = None
                run.result_message = (
                    f"config 解密失败: {type(exc).__name__}"
                )
                run.finished_at = _utcnow()
                run.duration_ms = 0
                run.host = _hostname()
                db.commit()
                _sync_instance_after_run(db, instance, run)
                db.commit()
                broker.close(run_id)
                return run_id

            try:
                fields = _load_fields(script)
                config = validate_config(config, fields)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "config schema 二次校验失败 instance={}: {}", instance_id, exc
                )
                run.status = "error"
                run.exit_code = None
                run.result_message = (
                    f"config schema 校验失败: {type(exc).__name__}: {exc}"
                )[:512]
                run.finished_at = _utcnow()
                run.duration_ms = 0
                run.host = _hostname()
                db.commit()
                _sync_instance_after_run(db, instance, run)
                db.commit()
                broker.close(run_id)
                return run_id

            # 资源信息提取(后面 session 关了用)
            script_slug = script.slug
            instance_name = instance.name
            timeout_sec = instance.timeout_sec or script.default_timeout_sec
            max_retries = instance.max_retries
            retry_interval_sec = instance.retry_interval_sec
            script_dir = Path(script.manifest_path).parent.resolve()
            data_dir = (
                settings.app_data_dir / "scripts" / script_slug / str(instance_id)
            ).resolve()
            # env passthrough 解析(从 manifest re-parse 以拿 runtime)
            env_passthrough = _extract_env_passthrough(script)

            # 确保 data_dir 存在
            try:
                data_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:  # pragma: no cover
                logger.warning("data_dir 创建失败 {}: {}", data_dir, exc)

            # ===== [7] status=running + 广播 =====
            run.status = "running"
            run.host = _hostname()
            db.commit()
            broker.publish_status(run_id, {"status": "running", "run_id": run_id})

        # ===== [5-6] 准备 RunContext + 启动子进程(session 已关) =====
        ctx = RunContextPayload(
            run_id=run_id,
            instance_id=instance_id,
            instance_name=instance_name,
            script_slug=script_slug,
            script_dir=str(script_dir),
            data_dir=str(data_dir),
            timeout_sec=timeout_sec,
            trigger_type=trigger_type,
            attempt=attempt,
        )

        # ===== [8-10] 执行 + 收集 =====
        result = await _run_subprocess(
            script_dir=script_dir,
            config=config,
            context=ctx,
            timeout_sec=timeout_sec,
            env_passthrough=env_passthrough,
            broker_publish=lambda stream, line: broker.publish(
                run_id, stream, line
            ),
        )

        # ===== 写回 runs + instance 冗余字段 =====
        with SessionLocal() as db:
            run = db.get(Run, run_id)
            instance = db.get(Instance, instance_id)
            if run is None:
                logger.error("run {} 在执行后消失了", run_id)
                broker.close(run_id)
                return run_id

            # audit Critical #2:若 run 已被 cancel_run 翻成 cancelled(外部信号已生效),
            # 保持 cancelled 状态;只把 stdout/stderr 之类的填上,不覆盖 status
            already_cancelled = run.status == "cancelled"
            if not already_cancelled:
                run.status = result["status"]
                run.exit_code = result["exit_code"]
                run.result_message = result["result_message"]
            run.result_data_json = (
                _safe_dump_json(result["result_data"]) if result["result_data"] else None
            )
            run.stdout = result["stdout"] or None
            run.stderr = result["stderr"] or None
            run.stdout_truncated = bool(result["stdout_truncated"])
            run.stderr_truncated = bool(result["stderr_truncated"])
            run.started_at = result["started_at"]
            if not already_cancelled or run.finished_at is None:
                run.finished_at = result["finished_at"]
            if not already_cancelled or run.duration_ms is None:
                run.duration_ms = result["duration_ms"]

            db.flush()
            if instance is not None:
                _sync_instance_after_run(db, instance, run)
            db.commit()

            # 广播 status 终态
            broker.publish_status(
                run_id,
                {
                    "status": run.status,
                    "exit_code": run.exit_code,
                    "duration_ms": run.duration_ms,
                    "result_message": run.result_message,
                },
            )

        # ===== [13] 失败重试(先判断,只在不重试时才发通知,避免每次重试都刷屏)=====
        # 设计稿 § 4.5:"最终通知按最后一次结果触发(避免每次重试都发通知刷屏)"
        # audit Critical #2:若被外部 cancel(cancel_run 在另一 session 翻了 run.status),
        # final_status 应是 'cancelled' → 不重试不发通知;否则按 result["status"] 来
        final_status = result["status"]
        try:
            with SessionLocal() as _check_db:
                _r = _check_db.get(Run, run_id)
                if _r is not None and _r.status == "cancelled":
                    final_status = "cancelled"
        except Exception:  # noqa: BLE001
            pass

        success = final_status == "success"
        will_retry = bool(
            scheduler is not None
            and should_retry(
                success=success,
                status=final_status,
                attempt=attempt,
                max_retries=max_retries,
            )
        )
        if will_retry:
            delay = compute_retry_delay(
                retry_interval_sec=retry_interval_sec,
                attempt=attempt,
            )
            try:
                scheduler.schedule_retry(
                    instance_id=instance_id,
                    parent_run_id=run_id,
                    next_attempt=attempt + 1,
                    delay_sec=delay,
                )
                logger.info(
                    "已调度重试 instance_id={} delay={}s next_attempt={}",
                    instance_id,
                    delay,
                    attempt + 1,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error("调度重试失败 instance={}: {}", instance_id, exc)

        # ===== [12] 通知 — 只在 retry 链结束(或本来就不会 retry)时发 =====
        # event 直接用 final_status — 'success'/'failure'/'error'/'timeout' 或 'cancelled'
        # cancelled 不在 dispatcher 支持的 event 内,会被 dispatcher 内部静默
        if not will_retry:
            await _dispatch_notification(run_id, final_status)

        # ===== [14] 关 broker =====
        broker.close(run_id)
        return run_id


async def _dispatch_notification(run_id: int, event: str) -> None:
    """安全调 dispatcher.dispatch_run_event — 任何异常都吃掉,不影响 executor。

    单独抽出来:
    - 自己拿 DB session,避免污染外层 session
    - 用模块级单例 cipher + apprise pool
    - 整体 try/except,失败只写日志(dispatcher 内部也有兜底,这里是双保险)
    """
    try:
        from app.core.crypto import get_cipher  # noqa: PLC0415
        from app.notifications.apprise_client import get_pool  # noqa: PLC0415
        from app.notifications.dispatcher import (  # noqa: PLC0415
            dispatch_run_event,
        )
    except ImportError as exc:
        logger.debug("通知模块未就绪,跳过 dispatch: {}", exc)
        return

    try:
        with SessionLocal() as db:
            run = db.get(Run, run_id)
            if run is None:
                logger.debug(
                    "dispatch_notification: run {} 不存在,跳过", run_id
                )
                return
            sent = await dispatch_run_event(
                db,
                run,
                event,
                cipher=get_cipher(),
                pool=get_pool(),
            )
            # dispatcher 自身只在成功 send 后 flush rule.last_fired_at;
            # 这里 commit 把变更落库
            db.commit()
            logger.debug(
                "dispatch_run_event run_id={} event={} sent={}",
                run_id,
                event,
                sent,
            )
    except Exception as exc:  # noqa: BLE001
        # dispatcher 内部已 try 兜底,这里再兜一次 — 任何 import / DB 问题都不会
        # 影响 executor 的主流程
        logger.warning(
            "dispatch_run_event 失败(已忽略,不影响 run) run_id={} event={} err={}",
            run_id,
            event,
            exc,
        )


# ============================================================
# 试运行 — 不写 runs,不发通知
# ============================================================
async def run_instance_test(instance_id: int) -> dict[str, Any]:
    """``POST /instances/{id}/test`` 用 — 试运行,返回 RunResult dict。

    不创建 run 行;不调通知;不竞争并发槽位(但仍受 sandbox 进程隔离)。
    """
    settings = get_settings()
    with SessionLocal() as db:
        instance: Instance | None = db.scalars(
            select(Instance).where(Instance.id == instance_id)
        ).one_or_none()
        if instance is None:
            raise ValueError(f"instance {instance_id} 不存在")
        script: Script | None = db.scalars(
            select(Script).where(Script.id == instance.script_id)
        ).one_or_none()
        if script is None:
            raise ValueError(f"script {instance.script_id} 不存在")

        config = (
            get_cipher().decrypt_dict(instance.config_blob)
            if instance.config_blob
            else {}
        )
        fields = _load_fields(script)
        config = validate_config(config, fields)

        timeout_sec = instance.timeout_sec or script.default_timeout_sec
        script_dir = Path(script.manifest_path).parent.resolve()
        data_dir = (
            settings.app_data_dir / "scripts" / script.slug / str(instance_id) / "_test"
        ).resolve()
        data_dir.mkdir(parents=True, exist_ok=True)
        env_passthrough = _extract_env_passthrough(script)

        ctx = RunContextPayload(
            run_id=0,  # test 没有 run_id
            instance_id=instance_id,
            instance_name=instance.name,
            script_slug=script.slug,
            script_dir=str(script_dir),
            data_dir=str(data_dir),
            timeout_sec=timeout_sec,
            trigger_type="test",
            attempt=1,
        )

    # session 已关,执行子进程
    return await _run_subprocess(
        script_dir=script_dir,
        config=config,
        context=ctx,
        timeout_sec=timeout_sec,
        env_passthrough=env_passthrough,
        broker_publish=None,
    )


# ============================================================
# 辅助
# ============================================================
def _hostname() -> str | None:
    try:
        import socket as _socket  # noqa: PLC0415

        return _socket.gethostname()[:64]
    except Exception:  # noqa: BLE001
        return None


def _safe_dump_json(data: Any) -> str:
    import json as _json

    try:
        text = _json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        text = _json.dumps(
            {"_unserializable": str(data)[:RESULT_DATA_MAX]},
            ensure_ascii=False,
        )
    if len(text) > RESULT_DATA_MAX:
        text = text[:RESULT_DATA_MAX] + "...[truncated]"
    return text


def _sync_instance_after_run(
    db: Session,
    instance: Instance,
    run: Run,
) -> None:
    """run 完成后同步 instance 冗余字段(§ 1.3 / 设计稿"总结要点 #2")。"""
    instance.last_run_id = run.id
    instance.last_run_status = run.status
    instance.last_run_at = run.finished_at or run.started_at
    instance.total_runs = (instance.total_runs or 0) + 1
    if run.status == "success":
        instance.total_successes = (instance.total_successes or 0) + 1
    db.flush()


def _finalize_skipped_run(db: Session, run_id: int, reason: str) -> None:
    """把"被跳过"的 pre-created run 标为 cancelled。"""
    run = db.get(Run, run_id)
    if run is None:
        return
    now = _utcnow()
    run.status = "cancelled"
    run.result_message = f"跳过:{reason}"
    run.finished_at = now
    run.duration_ms = 0
    run.host = _hostname()
    db.flush()


def _extract_env_passthrough(script: Script) -> list[str]:
    """从 manifest 文件 re-parse runtime.env_passthrough。

    fields_schema_json 里没存 runtime,所以这里直接重 parse 一次。
    成本很小,且 manifest 通常没几行。
    """
    try:
        from app.plugins.manifest import parse_manifest  # noqa: PLC0415

        manifest = parse_manifest(Path(script.manifest_path))
        return list(manifest.runtime.env_passthrough or [])
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "re-parse manifest 失败 slug={}: {}", script.slug, exc
        )
        return []
