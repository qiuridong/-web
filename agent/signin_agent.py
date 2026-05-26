"""signin-agent — 签到管家远程节点 agent。

设计稿:`进度/设计/远程VPS脚本执行调研.md` § 9
平台契约:配合 backend/app/api/v1/agent.py(4 个端点)+ backend/sandbox_runner.py

功能:
- HTTPS long-polling 从主面板拉 task(GET /api/v1/agent/poll?wait=30)
- 调本地 sandbox_runner.py 子进程跑脚本(独立 venv,Python 3.10+)
- 增量回传 stdout/stderr(POST /api/v1/agent/runs/{id}/stdout)
- 终态回传 result(POST /api/v1/agent/runs/{id}/result)
- 心跳每 30s(POST /api/v1/agent/heartbeat)

依赖:仅 ``httpx`` + ``PyYAML``(stdlib 之外)。不依赖 backend 任何模块。

启动:
    python3 signin_agent.py --config /etc/signin-agent/config.yaml
    # 或者命令行覆盖配置
    python3 signin_agent.py --master https://jb.aijiaxia.cc --token sa_xxx --scripts-dir /opt/signin-agent/scripts

systemd 部署见 ``install.sh``。

安全:
- node_token 在 ``/etc/signin-agent/config.yaml``,chmod 600
- 主面板下发的 task config 是**已解密的明文**(主密钥永不离开主面板)
- agent 跑完 task 立刻销毁 stdin 内容,不持久化 config
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import httpx
except ImportError:
    sys.stderr.write("❌ 缺少依赖 httpx,运行:pip install httpx pyyaml\n")
    sys.exit(1)

try:
    import yaml
except ImportError:
    sys.stderr.write("❌ 缺少依赖 PyYAML,运行:pip install httpx pyyaml\n")
    sys.exit(1)


# ============================================================
# 常量
# ============================================================
AGENT_VERSION = "1.0.0"
DEFAULT_CONFIG_PATH = "/etc/signin-agent/config.yaml"
RESULT_MARKER = "__RUN_RESULT__"

# 主面板 long polling wait 时长(server max 60,这里取 30)
POLL_WAIT_SEC = 30
# HTTP 总超时 = wait + 10(给网络余量)
POLL_HTTP_TIMEOUT = POLL_WAIT_SEC + 10
# poll 失败后重试基础间隔(指数退避)
POLL_RETRY_BASE_SEC = 5
POLL_RETRY_MAX_SEC = 60

# 心跳间隔
HEARTBEAT_INTERVAL_SEC = 30

# stdout 增量上报频率(每多少 ms 一批,避免高频请求)
STDOUT_FLUSH_INTERVAL_MS = 1500

# stdout 单批最大行数(避免单次 payload 太大)
STDOUT_BATCH_MAX_LINES = 50

# 子进程最大 timeout(从 task.timeout_sec 拿,这里是 fallback)
TASK_TIMEOUT_FALLBACK_SEC = 600

# MVP-2 · Bundle 同步
# 本地脚本目录里的版本 marker 文件名(存远端 bundle_sha256)
BUNDLE_MARKER_FILE = ".bundle_sha256"
# 拉 bundle.zip HTTP 超时(主面板 < 1MiB,60s 充足)
BUNDLE_FETCH_TIMEOUT_SEC = 60
# bundle 单个文件上限(防恶意 zip)— 与 backend MAX_FILE_BYTES 对齐 256 KiB
BUNDLE_FILE_MAX_BYTES = 256 * 1024
# bundle 总未压缩上限 — 与 backend MAX_ZIP_TOTAL_BYTES 对齐 1 MiB
BUNDLE_TOTAL_MAX_BYTES = 1 * 1024 * 1024


# ============================================================
# 配置加载
# ============================================================
@dataclass
class AgentConfig:
    master_url: str
    node_token: str
    scripts_dir: Path
    python_bin: str = "/usr/bin/python3"
    sandbox_runner: Path = Path("/opt/signin-agent/sandbox_runner.py")
    data_dir: Path = Path("/var/lib/signin-agent/data")
    timezone: str = "Asia/Shanghai"
    log_level: str = "INFO"

    @classmethod
    def load(cls, path: str | Path) -> AgentConfig:
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(f"config 文件不存在: {path}")
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentConfig:
        try:
            return cls(
                master_url=str(data["master_url"]).rstrip("/"),
                node_token=str(data["node_token"]),
                scripts_dir=Path(data["scripts_dir"]),
                python_bin=str(data.get("python_bin", "/usr/bin/python3")),
                sandbox_runner=Path(
                    data.get("sandbox_runner", "/opt/signin-agent/sandbox_runner.py")
                ),
                data_dir=Path(data.get("data_dir", "/var/lib/signin-agent/data")),
                timezone=str(data.get("timezone", "Asia/Shanghai")),
                log_level=str(data.get("log_level", "INFO")).upper(),
            )
        except KeyError as exc:
            raise ValueError(f"config 缺关键字段: {exc}") from exc

    def merge_args(self, args: argparse.Namespace) -> None:
        """命令行参数覆盖配置文件。"""
        if args.master:
            self.master_url = args.master.rstrip("/")
        if args.token:
            self.node_token = args.token
        if args.scripts_dir:
            self.scripts_dir = Path(args.scripts_dir)
        if args.python:
            self.python_bin = args.python
        if args.log_level:
            self.log_level = args.log_level.upper()


# ============================================================
# 全局停止标志(SIGTERM 触发)
# ============================================================
_stop_event = threading.Event()


def _on_signal(signum: int, _frame: Any) -> None:
    name = signal.Signals(signum).name
    logging.getLogger("signin-agent").info(
        f"收到信号 {name},准备退出..."
    )
    _stop_event.set()


# ============================================================
# Agent 主类
# ============================================================
class Agent:
    """signin-agent 主类 — 持有 httpx Session、配置、运行状态。"""

    def __init__(self, config: AgentConfig) -> None:
        self.config = config
        self.logger = logging.getLogger("signin-agent")
        self.client = httpx.Client(
            base_url=config.master_url,
            headers={
                "Authorization": f"Bearer {config.node_token}",
                "User-Agent": f"signin-agent/{AGENT_VERSION}",
            },
            timeout=POLL_HTTP_TIMEOUT,
            follow_redirects=False,
        )
        self._heartbeat_thread: threading.Thread | None = None
        self._poll_retry_sec = POLL_RETRY_BASE_SEC

    # ----------------------------------------------------------
    # 主循环
    # ----------------------------------------------------------
    def run(self) -> int:
        """主循环:启动心跳 + long-polling。

        return: exit code(0 正常停止,1 致命错误)
        """
        self.logger.info(
            f"signin-agent {AGENT_VERSION} 启动,master={self.config.master_url}"
        )
        # 启动前自检
        if not self._sanity_check():
            return 1

        # 启动心跳线程
        self._start_heartbeat()

        # 主 poll 循环
        try:
            while not _stop_event.is_set():
                try:
                    task = self._poll()
                except (httpx.TimeoutException, httpx.NetworkError) as exc:
                    self.logger.warning(
                        f"poll 网络错误({type(exc).__name__}): {exc},"
                        f"{self._poll_retry_sec}s 后重试"
                    )
                    self._wait_with_backoff()
                    continue
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 401:
                        self.logger.error(
                            "poll 401 — token 失效或节点被禁用,请检查 config"
                        )
                        # token 错就别再重试浪费请求
                        time.sleep(60)
                        continue
                    self.logger.error(
                        f"poll HTTP {exc.response.status_code}: {exc.response.text[:200]}"
                    )
                    self._wait_with_backoff()
                    continue
                except Exception as exc:  # noqa: BLE001
                    self.logger.exception(f"poll 未知异常: {exc}")
                    self._wait_with_backoff()
                    continue

                # 拿到任务就跑(单线程,串行)
                if task is not None:
                    # 重置 backoff(刚有任务 = 网络通畅)
                    self._poll_retry_sec = POLL_RETRY_BASE_SEC
                    try:
                        self._execute(task)
                    except Exception as exc:  # noqa: BLE001
                        # execute 内部已 try/catch + post_result,这里是最后兜底
                        self.logger.exception(
                            f"execute 未捕获异常 run_id={task.get('run_id')}: {exc}"
                        )
                else:
                    # 无任务 — 立即再 poll(server long-polling 已经等了 30s)
                    pass

        except KeyboardInterrupt:
            self.logger.info("被 Ctrl-C 中断,退出")
        finally:
            self.client.close()
            self.logger.info("signin-agent 退出")
        return 0

    # ----------------------------------------------------------
    # 自检(启动时跑一次)
    # ----------------------------------------------------------
    def _sanity_check(self) -> bool:
        ok = True

        # Python 检查
        if not Path(self.config.python_bin).is_file() and not _which(
            self.config.python_bin
        ):
            self.logger.error(f"python_bin 不存在: {self.config.python_bin}")
            ok = False
        else:
            self.logger.info(f"✓ python_bin: {self.config.python_bin}")

        # sandbox_runner 检查
        if not self.config.sandbox_runner.is_file():
            self.logger.error(
                f"sandbox_runner 不存在: {self.config.sandbox_runner};"
                f"请从主面板 backend/sandbox_runner.py 拷贝过来"
            )
            ok = False
        else:
            self.logger.info(
                f"✓ sandbox_runner: {self.config.sandbox_runner}"
            )

        # scripts_dir 检查
        if not self.config.scripts_dir.is_dir():
            self.logger.warning(
                f"scripts_dir 不存在,自动创建: {self.config.scripts_dir}"
            )
            try:
                self.config.scripts_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                self.logger.error(f"scripts_dir 创建失败: {exc}")
                ok = False
        else:
            scripts = [
                d.name for d in self.config.scripts_dir.iterdir() if d.is_dir()
            ]
            self.logger.info(
                f"✓ scripts_dir: {self.config.scripts_dir} (已部署 {len(scripts)} 个: {scripts})"
            )

        # data_dir 检查
        try:
            self.config.data_dir.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"✓ data_dir: {self.config.data_dir}")
        except OSError as exc:
            self.logger.error(f"data_dir 创建失败 {self.config.data_dir}: {exc}")
            ok = False

        # 主面板连通性测试 + token 验证(用 heartbeat)
        try:
            r = self.client.post(
                "/api/v1/agent/heartbeat",
                json={
                    "version": AGENT_VERSION,
                    "metadata": {"sanity_check": True},
                },
                timeout=10,
            )
            if r.status_code == 200:
                node_info = r.json()
                self.logger.info(
                    f"✓ 主面板连通,节点 id={node_info.get('node_id')} "
                    f"slug={node_info.get('node_slug')}"
                )
            elif r.status_code == 401:
                self.logger.error(
                    "✗ heartbeat 401 — node_token 失效或节点被禁用,请检查"
                )
                ok = False
            else:
                self.logger.error(
                    f"✗ heartbeat HTTP {r.status_code}: {r.text[:200]}"
                )
                ok = False
        except Exception as exc:  # noqa: BLE001
            self.logger.error(f"✗ heartbeat 测试失败: {exc}")
            ok = False

        return ok

    # ----------------------------------------------------------
    # 心跳后台线程
    # ----------------------------------------------------------
    def _start_heartbeat(self) -> None:
        def _loop() -> None:
            while not _stop_event.is_set():
                try:
                    r = self.client.post(
                        "/api/v1/agent/heartbeat",
                        json={
                            "version": AGENT_VERSION,
                            "metadata": _collect_node_metadata(),
                        },
                        timeout=10,
                    )
                    if r.status_code != 200:
                        self.logger.debug(
                            f"heartbeat HTTP {r.status_code}"
                        )
                except Exception as exc:  # noqa: BLE001
                    self.logger.debug(f"heartbeat 失败(忽略): {exc}")
                # 分块等待支持 SIGTERM 中断
                for _ in range(HEARTBEAT_INTERVAL_SEC):
                    if _stop_event.is_set():
                        break
                    time.sleep(1)

        t = threading.Thread(target=_loop, name="heartbeat", daemon=True)
        t.start()
        self._heartbeat_thread = t

    # ----------------------------------------------------------
    # poll
    # ----------------------------------------------------------
    def _poll(self) -> dict[str, Any] | None:
        r = self.client.get(
            "/api/v1/agent/poll",
            params={"wait": POLL_WAIT_SEC},
        )
        r.raise_for_status()
        data = r.json()
        return data.get("task")

    def _wait_with_backoff(self) -> None:
        # 分块等待,响应 SIGTERM
        for _ in range(self._poll_retry_sec):
            if _stop_event.is_set():
                return
            time.sleep(1)
        # 指数退避(上限 POLL_RETRY_MAX_SEC)
        self._poll_retry_sec = min(
            self._poll_retry_sec * 2, POLL_RETRY_MAX_SEC
        )

    # ----------------------------------------------------------
    # MVP-2 · 同步脚本 bundle(从主面板 Pull)
    # ----------------------------------------------------------
    def _ensure_script_synced(self, script_slug: str) -> None:
        """确保本地 ``scripts_dir/<slug>/`` 与主面板一致(按需同步)。

        流程:
        1. GET /api/v1/agent/scripts/<slug>/manifest → 拿 ``bundle_sha256``
        2. 比对本地 ``.bundle_sha256`` marker:一致 + main.py 存在 → return
        3. GET /api/v1/agent/scripts/<slug>/bundle.zip → 校验 sha256
        4. 解压到 tmp → 原子 ``os.replace`` 到 ``scripts_dir/<slug>/``
        5. 写新 ``.bundle_sha256`` marker

        失败时**只 log 不抛**,让 _execute 后续的 "main.py 不存在" 检查兜底报错。

        :raises RuntimeError: bundle sha256 校验失败 / zip slip 攻击(此时主动抛,
            因为主面板的 bundle 不可信 = 系统出大问题,不该继续跑)
        """
        script_dir = self.config.scripts_dir / script_slug
        marker_path = script_dir / BUNDLE_MARKER_FILE

        # 步 1: 拉 manifest
        try:
            r = self.client.get(
                f"/api/v1/agent/scripts/{script_slug}/manifest",
                timeout=15,
            )
            r.raise_for_status()
            manifest = r.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                self.logger.warning(
                    f"主面板没有脚本 {script_slug!r}(404),跳过同步"
                )
            else:
                self.logger.warning(
                    f"拉 manifest 失败 slug={script_slug} HTTP {exc.response.status_code}:"
                    f" {exc.response.text[:200]}"
                )
            return
        except Exception as exc:  # noqa: BLE001
            self.logger.warning(
                f"拉 manifest 网络错误 slug={script_slug}: {exc}"
            )
            return

        remote_sha = str(manifest.get("bundle_sha256") or "")
        remote_size = int(manifest.get("bundle_size") or 0)
        if not remote_sha:
            self.logger.warning(
                f"manifest 缺 bundle_sha256,跳过同步 slug={script_slug}"
            )
            return

        # 步 2: 比对本地 marker
        local_sha = ""
        if marker_path.is_file():
            try:
                local_sha = marker_path.read_text(encoding="utf-8").strip()
            except OSError:
                pass

        if local_sha == remote_sha and (script_dir / "main.py").is_file():
            self.logger.debug(
                f"脚本已最新 slug={script_slug} sha={remote_sha[:12]}"
            )
            return

        # 步 3: 拉 bundle.zip
        self.logger.info(
            f"⤓ 同步脚本 {script_slug}: local={local_sha[:12] or '(无)'} → "
            f"remote={remote_sha[:12]} ({remote_size} bytes)"
        )
        try:
            r = self.client.get(
                f"/api/v1/agent/scripts/{script_slug}/bundle.zip",
                timeout=BUNDLE_FETCH_TIMEOUT_SEC,
            )
            r.raise_for_status()
            bundle_bytes = r.content
        except Exception as exc:  # noqa: BLE001
            self.logger.error(f"拉取 bundle 失败 slug={script_slug}: {exc}")
            return

        if len(bundle_bytes) > BUNDLE_TOTAL_MAX_BYTES:
            self.logger.error(
                f"bundle 超过本地上限 {BUNDLE_TOTAL_MAX_BYTES} 字节"
                f" slug={script_slug} size={len(bundle_bytes)}"
            )
            return

        # 步 4: 校验 sha256
        actual_sha = hashlib.sha256(bundle_bytes).hexdigest()
        if actual_sha != remote_sha:
            raise RuntimeError(
                f"bundle sha256 不匹配 slug={script_slug} "
                f"expected={remote_sha[:16]} actual={actual_sha[:16]}"
            )

        # 步 5: 原子解压
        self.config.scripts_dir.mkdir(parents=True, exist_ok=True)
        tmp_dir = self.config.scripts_dir / f".tmp-{script_slug}-{int(time.time())}"
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)
        tmp_dir.mkdir()

        try:
            with zipfile.ZipFile(io.BytesIO(bundle_bytes), "r") as zf:
                # 安全校验
                for info in zf.infolist():
                    name = info.filename
                    if name.endswith("/"):
                        continue
                    # Zip slip 防御:绝对路径 / .. / 反斜杠
                    normalized = name.replace("\\", "/")
                    if normalized.startswith("/"):
                        raise RuntimeError(
                            f"bundle 含绝对路径条目: {name!r}"
                        )
                    if any(p == ".." for p in normalized.split("/")):
                        raise RuntimeError(
                            f"bundle 含 .. 路径段: {name!r}"
                        )
                    if info.file_size > BUNDLE_FILE_MAX_BYTES:
                        raise RuntimeError(
                            f"bundle 单文件 {name!r} {info.file_size} > 上限"
                            f" {BUNDLE_FILE_MAX_BYTES}"
                        )

                # 解压
                for info in zf.infolist():
                    if info.filename.endswith("/"):
                        continue
                    normalized = info.filename.replace("\\", "/")
                    target = tmp_dir / normalized
                    # 双保险:resolve 后必须在 tmp_dir 下
                    try:
                        target.resolve().relative_to(tmp_dir.resolve())
                    except ValueError:
                        raise RuntimeError(
                            f"解压逃出 tmp_dir: {target}"
                        )
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(info, "r") as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst, length=64 * 1024)

            # 写 marker
            (tmp_dir / BUNDLE_MARKER_FILE).write_text(
                remote_sha, encoding="utf-8"
            )

            # 备份旧目录(若存在)
            backup_dir: Path | None = None
            if script_dir.exists():
                backup_dir = (
                    self.config.scripts_dir
                    / f".backup-{script_slug}-{int(time.time())}"
                )
                os.replace(script_dir, backup_dir)

            # 原子搬过去
            try:
                os.replace(tmp_dir, script_dir)
            except OSError as exc:
                # 回滚
                if backup_dir is not None and backup_dir.exists():
                    try:
                        os.replace(backup_dir, script_dir)
                    except OSError:
                        self.logger.exception(
                            f"回滚失败 backup={backup_dir} target={script_dir}"
                        )
                raise RuntimeError(
                    f"原子替换失败 slug={script_slug}: {exc}"
                ) from exc

            # 成功 → 清旧备份
            if backup_dir is not None and backup_dir.exists():
                try:
                    shutil.rmtree(backup_dir)
                except OSError as exc:
                    self.logger.warning(
                        f"清旧备份失败(可手动 rm) {backup_dir}: {exc}"
                    )

            self.logger.info(
                f"✓ 脚本同步完成 {script_slug} sha={remote_sha[:12]}"
            )

        except Exception:
            # 清 tmp(只清没被 rename 走的情况)
            if tmp_dir.exists():
                try:
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                except OSError:
                    pass
            raise

    # ----------------------------------------------------------
    # 执行 task
    # ----------------------------------------------------------
    def _execute(self, task: dict[str, Any]) -> None:
        run_id = int(task["run_id"])
        instance_id = int(task["instance_id"])
        script_slug = str(task["script_slug"])
        timeout_sec = int(task.get("timeout_sec") or TASK_TIMEOUT_FALLBACK_SEC)

        self.logger.info(
            f"▶ run {run_id} (instance {instance_id} / script {script_slug}) "
            f"timeout={timeout_sec}s"
        )

        # MVP-2 · 拉脚本(按需同步,sha256 比对一致则跳过)
        # 失败时不抛(只 log),让下面 main.py 检查兜底报错
        try:
            self._ensure_script_synced(script_slug)
        except Exception as exc:  # noqa: BLE001
            self.logger.error(
                f"脚本同步 raised(本次跳过同步,试用本地版本) "
                f"slug={script_slug}: {exc}"
            )

        # 检查脚本本地是否存在(同步失败 / 主面板没此脚本时的兜底)
        script_dir = self.config.scripts_dir / script_slug
        if not (script_dir / "main.py").is_file():
            msg = (
                f"脚本未部署到 agent 节点:{script_dir}/main.py 不存在。"
                "Pull 同步也失败 — 请到主面板 web 检查脚本是否已上传,"
                "或手动 scp 同步过来。"
            )
            self.logger.error(msg)
            self._post_result(
                run_id,
                {
                    "success": False,
                    "status": "error",
                    "exit_code": 127,
                    "duration_ms": 0,
                    "message": msg,
                    "data": {"error_class": "ScriptNotFound", "slug": script_slug},
                    "stdout": "",
                    "stderr": msg,
                },
            )
            return

        # data_dir(实例独立目录,持久化)
        instance_data_dir = (
            self.config.data_dir / f"instance-{instance_id}"
        )
        instance_data_dir.mkdir(parents=True, exist_ok=True)

        # 构造 sandbox_runner 的 stdin JSON
        stdin_payload = json.dumps(
            {
                "config": task.get("config") or {},
                "context": {
                    "run_id": run_id,
                    "instance_id": instance_id,
                    "instance_name": task.get("instance_name", ""),
                    "script_slug": script_slug,
                    "script_dir": str(script_dir.resolve()),
                    "data_dir": str(instance_data_dir.resolve()),
                    "timeout_sec": timeout_sec,
                    "trigger_type": task.get("trigger_type", "manual"),
                    "attempt": int(task.get("attempt", 1)),
                },
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )

        # 构造 env(白名单透传)
        env = os.environ.copy()
        env["TZ"] = self.config.timezone
        env["PYTHONIOENCODING"] = "utf-8"
        env["SCRIPT_SLUG"] = script_slug
        for key in task.get("env_passthrough") or []:
            if key in os.environ:
                env[key] = os.environ[key]
        # 主面板 PYTHONPATH 不透传,避免脚本 import app.*

        # 启动子进程
        started_at = time.monotonic()
        try:
            proc = subprocess.Popen(
                [self.config.python_bin, "-u", str(self.config.sandbox_runner)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                cwd=str(script_dir),
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except (FileNotFoundError, PermissionError) as exc:
            msg = f"启动 sandbox_runner 失败: {type(exc).__name__}: {exc}"
            self.logger.error(msg)
            self._post_result(
                run_id,
                {
                    "success": False,
                    "status": "error",
                    "exit_code": 126,
                    "duration_ms": 0,
                    "message": msg,
                    "data": {"error_class": type(exc).__name__},
                    "stdout": "",
                    "stderr": msg,
                },
            )
            return

        # 喂 stdin,立即关
        try:
            proc.stdin.write(stdin_payload + "\n")
            proc.stdin.flush()
            proc.stdin.close()
        except (BrokenPipeError, OSError) as exc:
            self.logger.warning(f"stdin 写入失败(子进程可能立刻退): {exc}")

        # 开 2 个后台线程读 stdout / stderr,各自批量回传
        stdout_lines: list[str] = []
        stderr_lines: list[str] = []
        stdout_seq = [0]
        stderr_seq = [0]
        stop_readers = threading.Event()

        def _drain(
            pipe,
            stream_name: str,
            collector: list[str],
            seq_ref: list[int],
        ) -> None:
            buffer: list[str] = []
            last_flush = time.monotonic()
            for line in pipe:
                line_rstripped = line.rstrip("\r\n")
                collector.append(line_rstripped)
                buffer.append(line_rstripped)
                now = time.monotonic()
                if (
                    len(buffer) >= STDOUT_BATCH_MAX_LINES
                    or (now - last_flush) * 1000 >= STDOUT_FLUSH_INTERVAL_MS
                ):
                    self._post_stdout(
                        run_id, stream_name, buffer, seq_ref[0]
                    )
                    seq_ref[0] += 1
                    buffer.clear()
                    last_flush = now
            # 收尾 flush
            if buffer:
                self._post_stdout(
                    run_id, stream_name, buffer, seq_ref[0]
                )
                seq_ref[0] += 1
            stop_readers.set()

        t_out = threading.Thread(
            target=_drain,
            args=(proc.stdout, "stdout", stdout_lines, stdout_seq),
            name=f"reader-stdout-{run_id}",
            daemon=True,
        )
        t_err = threading.Thread(
            target=_drain,
            args=(proc.stderr, "stderr", stderr_lines, stderr_seq),
            name=f"reader-stderr-{run_id}",
            daemon=True,
        )
        t_out.start()
        t_err.start()

        # 等子进程结束,带 timeout
        try:
            exit_code = proc.wait(timeout=timeout_sec)
            timed_out = False
        except subprocess.TimeoutExpired:
            self.logger.warning(
                f"run {run_id} 超时 {timeout_sec}s,强杀子进程"
            )
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
            exit_code = proc.returncode if proc.returncode is not None else -1
            timed_out = True

        # 等 reader 线程收尾
        t_out.join(timeout=10)
        t_err.join(timeout=10)

        duration_ms = int((time.monotonic() - started_at) * 1000)

        # 解析 stdout 找 __RUN_RESULT__
        stdout_full = "\n".join(stdout_lines)
        stderr_full = "\n".join(stderr_lines)
        result_payload = _parse_result_marker(stdout_lines)

        # 决定终态
        if timed_out:
            status_str = "timeout"
            success = False
            message = f"超时 {timeout_sec}s,子进程被强杀"
            data = {"error_class": "TimeoutExpired", "timeout_sec": timeout_sec}
        elif result_payload is not None:
            success = bool(result_payload.get("success", False))
            status_str = "success" if success else "failure"
            message = str(result_payload.get("message", ""))[:512]
            data = result_payload.get("data") or {}
        elif exit_code != 0:
            success = False
            status_str = "error"
            message = (
                f"子进程 exit={exit_code} 且未输出 __RUN_RESULT__,"
                f"stderr 尾部: {stderr_full[-200:] if stderr_full else '(空)'}"
            )
            data = {"error_class": "NoResultMarker", "exit_code": exit_code}
        else:
            # exit=0 但没 RUN_RESULT 也算异常
            success = False
            status_str = "error"
            message = "子进程 exit=0 但未输出 __RUN_RESULT__"
            data = {"error_class": "NoResultMarker", "exit_code": 0}

        # truncate stdout/stderr(主面板限 256 KiB,我们这里也截一下避免大 payload)
        MAX_STREAM_BYTES = 262144
        stdout_truncated = False
        stderr_truncated = False
        if len(stdout_full.encode("utf-8")) > MAX_STREAM_BYTES:
            stdout_full = stdout_full.encode("utf-8")[-MAX_STREAM_BYTES:].decode(
                "utf-8", errors="replace"
            )
            stdout_truncated = True
        if len(stderr_full.encode("utf-8")) > MAX_STREAM_BYTES:
            stderr_full = stderr_full.encode("utf-8")[-MAX_STREAM_BYTES:].decode(
                "utf-8", errors="replace"
            )
            stderr_truncated = True

        self.logger.info(
            f"◀ run {run_id} 结束 status={status_str} exit={exit_code} "
            f"duration={duration_ms}ms msg={message[:80]!r}"
        )

        self._post_result(
            run_id,
            {
                "success": success,
                "status": status_str,
                "exit_code": exit_code,
                "duration_ms": duration_ms,
                "message": message,
                "data": data,
                "stdout": stdout_full,
                "stderr": stderr_full,
                "stdout_truncated": stdout_truncated,
                "stderr_truncated": stderr_truncated,
            },
        )

    # ----------------------------------------------------------
    # API POST helpers
    # ----------------------------------------------------------
    def _post_stdout(
        self, run_id: int, stream: str, lines: list[str], seq: int
    ) -> None:
        try:
            self.client.post(
                f"/api/v1/agent/runs/{run_id}/stdout",
                json={"stream": stream, "lines": list(lines), "seq": seq},
                timeout=15,
            )
        except Exception as exc:  # noqa: BLE001
            self.logger.debug(
                f"post_stdout 失败(忽略,终态会带完整 stdout): {exc}"
            )

    def _post_result(self, run_id: int, payload: dict[str, Any]) -> None:
        # 失败要重试几次,因为这是关键状态
        for attempt in range(1, 6):
            try:
                r = self.client.post(
                    f"/api/v1/agent/runs/{run_id}/result",
                    json=payload,
                    timeout=30,
                )
                if r.status_code == 204:
                    return
                self.logger.warning(
                    f"post_result 第 {attempt} 次 HTTP {r.status_code}: "
                    f"{r.text[:200]}"
                )
            except Exception as exc:  # noqa: BLE001
                self.logger.warning(
                    f"post_result 第 {attempt} 次失败: {exc}"
                )
            # 指数退避
            time.sleep(min(5 * (2 ** (attempt - 1)), 60))

        self.logger.error(
            f"post_result run {run_id} 5 次全失败,run 在主面板将保持 running 状态"
        )


# ============================================================
# helpers
# ============================================================
def _which(cmd: str) -> str | None:
    """简易 shutil.which 替代(避免 import shutil)。"""
    for p in os.environ.get("PATH", "").split(os.pathsep):
        full = Path(p) / cmd
        if full.is_file() and os.access(full, os.X_OK):
            return str(full)
    return None


def _collect_node_metadata() -> dict[str, Any]:
    """收集节点基本信息上报。"""
    meta: dict[str, Any] = {
        "agent_version": AGENT_VERSION,
        "python_version": sys.version.split()[0],
        "platform": sys.platform,
    }
    try:
        import platform

        meta["os"] = platform.platform()
        meta["hostname"] = platform.node()
    except Exception:  # noqa: BLE001
        pass
    return meta


def _parse_result_marker(stdout_lines: list[str]) -> dict[str, Any] | None:
    """从 stdout 倒序找 ``__RUN_RESULT__{...}`` 行,返回解析后的 dict。"""
    for line in reversed(stdout_lines):
        if line.startswith(RESULT_MARKER):
            try:
                return json.loads(line[len(RESULT_MARKER):])
            except json.JSONDecodeError:
                return None
    return None


# ============================================================
# main
# ============================================================
def main() -> int:
    parser = argparse.ArgumentParser(
        prog="signin-agent",
        description="签到管家远程节点 agent(v1.0.0,Pull + Long Polling)",
    )
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help=f"配置文件路径(默认 {DEFAULT_CONFIG_PATH})",
    )
    parser.add_argument("--master", help="覆盖 master_url")
    parser.add_argument("--token", help="覆盖 node_token")
    parser.add_argument("--scripts-dir", help="覆盖 scripts_dir")
    parser.add_argument("--python", help="覆盖 python_bin")
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="覆盖 log_level",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"signin-agent {AGENT_VERSION}",
    )
    args = parser.parse_args()

    # 加载配置(允许 --master + --token 不靠文件)
    if Path(args.config).is_file():
        try:
            config = AgentConfig.load(args.config)
        except (FileNotFoundError, ValueError, yaml.YAMLError) as exc:
            sys.stderr.write(f"❌ 配置加载失败: {exc}\n")
            return 1
    else:
        # 全命令行模式
        if not (args.master and args.token):
            sys.stderr.write(
                f"❌ 配置文件不存在({args.config}),"
                f"且未提供 --master / --token\n"
            )
            return 1
        config = AgentConfig(
            master_url=args.master.rstrip("/"),
            node_token=args.token,
            scripts_dir=Path(args.scripts_dir or "/opt/signin-agent/scripts"),
            python_bin=args.python or "/usr/bin/python3",
        )
    config.merge_args(args)

    # 日志
    logging.basicConfig(
        level=config.log_level,
        format="%(asctime)s [%(levelname)s] [%(threadName)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 信号处理
    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    agent = Agent(config)
    return agent.run()


if __name__ == "__main__":
    sys.exit(main())
