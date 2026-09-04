"""动漫共和国每日签到：ADB + 登录保活 + 本地验证码识别。

1.2.9 修复冷启动公告关闭后停在未识别底栏页，并从语义底栏继续导航。
验证码识别器只提交高置信乘法题，加/减/除法和不完整 token 链全部刷新。
"""

# Chinese UI copy intentionally uses full-width punctuation.
# ruff: noqa: RUF001, RUF002, RUF003

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import shutil
import signal
import subprocess
import time
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from helpers.emulator_lifecycle import (
    LOCK_PATH,
    EmulatorLifecycle,
    EmulatorLifecycleError,
    ExclusiveFileLock,
)

PACKAGE = "com.shizi.tool.p3"
LOCKED_SERIAL = "emulator-6554"
LOCKED_WIDTH = 720
LOCKED_HEIGHT = 1280
LOCKED_DENSITY = 320
LOCKED_API = "34"
LOCKED_VERSION = "1.0.0.7"
MAIN_ACTIVITY = "app.video.guoguo.MainActivity"
SPLASH_ACTIVITY = "app.video.guoguo.SplashActivity"

OCR_REQUIREMENTS = (
    "ddddocr==1.6.1",
    "onnxruntime>=1.20,<2",
    "opencv-python-headless>=4.10,<5",
    "Pillow>=10,<13",
)
OCR_MARKER_VERSION = "dmgongheguo-ocr-v1"
ACCOUNT_BINDING_PATH = "/data/local/tmp/.dmgongheguo-account-binding-v1.json"
ACCOUNT_BINDING_SCHEMA = 1
TASK_UI_HIERARCHY_PATH = "/data/local/tmp/.dmgongheguo-task-ui.xml"
ROOT_NAV_TABS = frozenset({"discover", "channel", "task", "my"})


@dataclass
class RunResult:
    success: bool
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)


class ScriptError(RuntimeError):
    pass


class AdbError(ScriptError):
    pass


class OcrRuntimeError(ScriptError):
    pass


def _normalized_account(config: dict[str, Any]) -> str:
    account = str(config.get("account") or "").strip().lower()
    if not account:
        raise ScriptError("必须配置邮箱账号，才能绑定 Emulator 与登录身份")
    if not re.fullmatch(r"[a-z0-9._-]+@[a-z0-9.-]+", account):
        raise ScriptError("account 不是受支持的邮箱格式")
    return account


def _account_hash(account: str) -> str:
    return hashlib.sha256(
        ("dmgongheguo-account-v1\0" + account).encode("utf-8")
    ).hexdigest()


def _expected_binding(account: str, avd_name: str) -> dict[str, Any]:
    return {
        "schema": ACCOUNT_BINDING_SCHEMA,
        "package": PACKAGE,
        "avd_name": avd_name,
        "account_sha256": _account_hash(account),
    }


def _read_account_binding(adb: AdbClient) -> dict[str, Any] | None:
    result = adb.run(
        "shell",
        "cat",
        ACCOUNT_BINDING_PATH,
        timeout=10,
        check=False,
        sensitive=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).lower()
        if "no such file" in detail or "not found" in detail:
            return None
        raise ScriptError("读取 Emulator 账户绑定标记失败")
    try:
        value = json.loads(result.stdout)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ScriptError("Emulator 账户绑定标记损坏，拒绝覆盖") from exc
    if not isinstance(value, dict):
        raise ScriptError("Emulator 账户绑定标记格式错误")
    return value


def _validate_account_binding(
    binding: dict[str, Any], expected: dict[str, Any]
) -> None:
    _validate_binding_container(binding, expected)
    if binding.get("account_sha256") != expected.get("account_sha256"):
        raise ScriptError(
            "Emulator 与当前实例的账号绑定不匹配；"
            "请开启账号变化自动换绑，或恢复原账号配置"
        )


def _validate_binding_container(
    binding: dict[str, Any], expected: dict[str, Any]
) -> None:
    """先验证绑定确属当前包和 AVD，再决定是否允许账号换绑。"""

    for key in ("schema", "package", "avd_name"):
        value = expected[key]
        if binding.get(key) != value:
            raise ScriptError(
                "Emulator 账户绑定不匹配：当前 App/AVD 与标记不一致；"
                "已停止自动换绑和签到"
            )
    account_hash = str(binding.get("account_sha256") or "")
    if re.fullmatch(r"[0-9a-f]{64}", account_hash) is None:
        raise ScriptError("Emulator 账户绑定缺少有效的账号哈希")
    signature = str(binding.get("profile_signature") or "")
    if re.fullmatch(r"[0-9a-f]{64}", signature) is None:
        raise ScriptError("Emulator 账户绑定缺少有效的昵称字形签名")


def _binding_matches_account(
    binding: dict[str, Any], expected: dict[str, Any]
) -> bool:
    return binding.get("account_sha256") == expected.get("account_sha256")


def _require_login_password(config: dict[str, Any]) -> str:
    password = str(config.get("password") or "")
    if not password:
        raise ScriptError("自动登录或账号换绑需要在实例中配置登录密码")
    return password


def _reset_app_for_account_rebind(adb: AdbClient) -> None:
    """在已验证的 AVD 内清除旧 App 会话和旧绑定，不触碰 APK/AVD。"""

    adb.logger.info("自动换绑：正在停止旧 App")
    adb.run(
        "shell",
        "am",
        "force-stop",
        PACKAGE,
        timeout=15,
        sensitive=True,
    )
    cleared = adb.run(
        "shell",
        "pm",
        "clear",
        "--user",
        "current",
        PACKAGE,
        timeout=45,
        check=False,
        sensitive=True,
    )
    if cleared.returncode != 0 or "success" not in cleared.stdout.lower():
        raise ScriptError("清理旧 App 账户数据失败，已停止自动换绑")
    adb.logger.info("自动换绑：旧 App 数据已清理")
    adb.run(
        "shell",
        "rm",
        "-f",
        ACCOUNT_BINDING_PATH,
        timeout=10,
        sensitive=True,
    )
    adb.run("shell", "sync", timeout=20, sensitive=True)
    if _read_account_binding(adb) is not None:
        raise ScriptError("清理后旧账户绑定标记仍然存在，已停止自动换绑")
    # ``pm clear`` 返回 Success 时，旧 Activity 的最后一帧仍可能短暂留在
    # framebuffer / dumpsys activity 中。先切回 HOME，避免后续启动检测把这张
    # 旧的“已登录”画面当成清理后的真实状态；新 App 随后会被强制重新启动。
    adb.key("3")
    time.sleep(1.0)
    adb.logger.info("自动换绑：旧账户绑定标记已清理并落盘")


def _profile_signature(worker: OcrWorker, png: bytes) -> str:
    result = worker.request("profile", png)
    signature = str(result.get("profile_signature") or "")
    if re.fullmatch(r"[0-9a-f]{64}", signature) is None:
        raise ScriptError("无法提取当前登录用户的昵称字形签名")
    return signature


def _verify_profile_signature(binding: dict[str, Any], actual: str) -> None:
    if binding.get("profile_signature") != actual:
        raise ScriptError(
            "当前 App 登录用户与此 Emulator 的已绑定身份不一致，已停止签到"
        )


def _write_account_binding(
    adb: AdbClient,
    context: Any,
    expected: dict[str, Any],
    profile_signature: str,
) -> dict[str, Any]:
    binding = {**expected, "profile_signature": profile_signature}
    data_dir = Path(context.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    upload = data_dir / f".account-binding-upload-{os.getpid()}.json"
    try:
        upload.write_text(
            json.dumps(binding, ensure_ascii=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        if os.name != "nt":
            upload.chmod(0o600)
        adb.run(
            "push",
            str(upload),
            ACCOUNT_BINDING_PATH,
            timeout=20,
            sensitive=True,
        )
        adb.run(
            "shell",
            "chmod",
            "600",
            ACCOUNT_BINDING_PATH,
            timeout=10,
            sensitive=True,
        )
        adb.run("shell", "sync", timeout=20, sensitive=True)
    finally:
        upload.unlink(missing_ok=True)
    written = _read_account_binding(adb)
    if written is None:
        raise ScriptError("写入 Emulator 账户绑定标记后复核失败")
    _validate_account_binding(written, expected)
    _verify_profile_signature(written, profile_signature)
    return written


@contextmanager
def _sigterm_cleanup_guard():
    """把 Agent 的 SIGTERM 转成可展开 finally 的 SystemExit。"""

    if os.name == "nt":
        yield
        return
    previous = signal.getsignal(signal.SIGTERM)

    def _terminate(signum: int, _frame: Any) -> None:
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, _terminate)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)


def _bounded_int(config: dict[str, Any], key: str, default: int, low: int, high: int) -> int:
    try:
        value = int(config.get(key, default))
    except (TypeError, ValueError) as exc:
        raise ScriptError(f"{key} 必须是整数") from exc
    if not low <= value <= high:
        raise ScriptError(f"{key} 必须在 {low}..{high} 范围内")
    return value


def _bounded_float(
    config: dict[str, Any], key: str, default: float, low: float, high: float
) -> float:
    try:
        value = float(config.get(key, default))
    except (TypeError, ValueError) as exc:
        raise ScriptError(f"{key} 必须是数字") from exc
    if not low <= value <= high:
        raise ScriptError(f"{key} 必须在 {low}..{high} 范围内")
    return value


class AdbClient:
    def __init__(self, adb_path: str, serial: str, logger: logging.Logger) -> None:
        if serial != LOCKED_SERIAL:
            raise ScriptError(f"本脚本只允许设备 {LOCKED_SERIAL}")
        self.adb_path = adb_path
        self.serial = serial
        self.logger = logger

    def _command(self, *args: str) -> list[str]:
        return [self.adb_path, "-s", self.serial, *args]

    def run(
        self,
        *args: str,
        timeout: float = 20,
        check: bool = True,
        sensitive: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        try:
            result = subprocess.run(
                self._command(*args),
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
        except (FileNotFoundError, PermissionError, subprocess.TimeoutExpired) as exc:
            raise AdbError(f"ADB 执行失败: {type(exc).__name__}") from exc
        if check and result.returncode != 0:
            detail = "已隐藏" if sensitive else result.stderr.strip()[-240:]
            raise AdbError(f"ADB exit={result.returncode}: {detail}")
        return result

    def screenshot(self) -> bytes:
        try:
            result = subprocess.run(
                self._command("exec-out", "screencap", "-p"),
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=25,
                check=False,
            )
        except (FileNotFoundError, PermissionError, subprocess.TimeoutExpired) as exc:
            raise AdbError(f"截图失败: {type(exc).__name__}") from exc
        if result.returncode != 0 or not result.stdout.startswith(b"\x89PNG"):
            raise AdbError("截图失败或返回的不是 PNG")
        return result.stdout

    def tap(self, x: int, y: int) -> None:
        self.run("shell", "input", "tap", str(x), str(y))

    def key(self, keycode: str) -> None:
        self.run("shell", "input", "keyevent", keycode)

    def select_all(self) -> None:
        self.run("shell", "input", "keycombination", "113", "29")

    def type_text(self, value: str) -> None:
        """输入本项目所需的邮箱、密码和整数答案，不把内容写入日志。"""

        if not value or len(value) > 160:
            raise ScriptError("输入内容为空或过长")
        # 字母数字段一次输入；容易被 Android input shell 解释的字符逐个 keyevent。
        buffer: list[str] = []

        def flush() -> None:
            if buffer:
                self.run(
                    "shell",
                    "input",
                    "text",
                    "".join(buffer),
                    sensitive=True,
                )
                buffer.clear()

        keycodes = {"@": "77", ".": "56", "-": "69"}
        for char in value:
            if char.isascii() and char.isalnum():
                buffer.append(char)
                continue
            flush()
            if char in keycodes:
                self.key(keycodes[char])
            else:
                raise ScriptError(
                    "当前安全输入器仅支持字母、数字以及 @ . -；请调整密码后再配置"
                )
        flush()


def _find_uv(configured: str | None) -> str:
    candidates = [configured, shutil.which("uv"), "/root/.local/bin/uv"]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    raise OcrRuntimeError("未找到 uv；UK 节点应使用 /root/.local/bin/uv")


def _venv_python(venv: Path) -> Path:
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def _runtime_healthy(python: Path, solver: Path, assets: Path) -> bool:
    if not python.is_file():
        return False
    try:
        result = subprocess.run(
            [str(python), str(solver), "--self-check", "--assets", str(assets)],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=45,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and '"ok": true' in result.stdout.lower()


def ensure_ocr_runtime(
    config: dict[str, Any], context: Any, logger: logging.Logger
) -> tuple[Path, Path, Path]:
    script_dir = Path(context.script_dir)
    solver = script_dir / "helpers" / "captcha_solver.py"
    assets = script_dir / "assets"
    if not solver.is_file() or not assets.is_dir():
        raise OcrRuntimeError("验证码识别器或 assets 缺失")

    configured = str(config.get("ocr_python") or "").strip()
    if configured:
        python = Path(configured)
        if _runtime_healthy(python, solver, assets):
            return python, solver, assets
        raise OcrRuntimeError("ocr_python 自检失败")

    data_dir = Path(context.data_dir)
    venv = data_dir / ".ocr-venv"
    python = _venv_python(venv)
    marker = venv / ".dmgongheguo-ocr-version"
    if (
        marker.is_file()
        and marker.read_text("utf-8").strip() == OCR_MARKER_VERSION
        and _runtime_healthy(python, solver, assets)
    ):
        return python, solver, assets

    if not bool(config.get("auto_install_ocr", True)):
        raise OcrRuntimeError("OCR 运行时不存在，且 auto_install_ocr 已关闭")

    uv = _find_uv(str(config.get("uv_path") or "").strip() or None)
    logger.info("首次运行：在实例 data_dir 安装独立 Python 3.12 OCR 环境…")
    venv.parent.mkdir(parents=True, exist_ok=True)
    commands = (
        [uv, "venv", "--python", "3.12", "--seed", str(venv)],
        [uv, "pip", "install", "--python", str(python), *OCR_REQUIREMENTS],
    )
    for command in commands:
        result = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
            check=False,
        )
        if result.returncode != 0:
            raise OcrRuntimeError(
                f"OCR 环境安装失败 exit={result.returncode}: {result.stdout[-400:]}"
            )
    marker.write_text(OCR_MARKER_VERSION + "\n", encoding="utf-8")
    if not _runtime_healthy(python, solver, assets):
        raise OcrRuntimeError("OCR 环境安装后自检仍失败")
    logger.info("OCR 环境安装完成；后续运行复用缓存")
    return python, solver, assets


class OcrWorker:
    def __init__(self, python: Path, solver: Path, assets: Path) -> None:
        self.process = subprocess.Popen(
            [str(python), str(solver), "--server", "--assets", str(assets)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        self._request_id = 0

    def close(self) -> None:
        if self.process.stdin:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)

    def request(self, mode: str, image: bytes, **values: Any) -> dict[str, Any]:
        if self.process.poll() is not None:
            stderr = self.process.stderr.read()[-500:] if self.process.stderr else ""
            raise OcrRuntimeError(f"OCR worker 已退出: {stderr}")
        self._request_id += 1
        payload = {
            "id": self._request_id,
            "mode": mode,
            "image_b64": base64.b64encode(image).decode("ascii"),
            **values,
        }
        assert self.process.stdin is not None
        assert self.process.stdout is not None
        self.process.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        if not line:
            stderr = self.process.stderr.read()[-500:] if self.process.stderr else ""
            raise OcrRuntimeError(f"OCR worker 无响应: {stderr}")
        response = json.loads(line)
        if not response.get("ok"):
            raise OcrRuntimeError(
                f"OCR worker {response.get('error')}: {response.get('message')}"
            )
        result = response.get("result")
        if not isinstance(result, dict):
            raise OcrRuntimeError("OCR worker 返回格式错误")
        return result

    def __enter__(self) -> OcrWorker:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def _wait_surface(
    adb: AdbClient,
    worker: OcrWorker,
    expected: set[str],
    *,
    timeout: float,
    interval: float = 1.0,
) -> tuple[str, dict[str, Any], bytes]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {"surface": "unknown"}
    last_png = b""
    while time.monotonic() < deadline:
        last_png = adb.screenshot()
        last = worker.request("ui", last_png)
        surface = str(last.get("surface"))
        if surface in expected:
            return surface, last, last_png
        time.sleep(interval)
    raise ScriptError(
        f"等待界面超时 expected={sorted(expected)} last={last.get('surface')}"
    )


def _node_in_task_header(node: ET.Element) -> bool:
    """只接受任务页顶部状态区域，排除底栏和奖励说明里的同名文字。"""

    match = re.fullmatch(
        r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]",
        str(node.attrib.get("bounds") or ""),
    )
    if match is None:
        return False
    left, top, right, bottom = (int(value) for value in match.groups())
    return 180 <= left < right <= 540 and 120 <= top < bottom <= 360


def _task_surface_from_accessibility(xml_text: str) -> dict[str, Any]:
    """从 Flutter accessibility 语义树提取“今日待签/已签”的直接证据。"""

    try:
        root = ET.fromstring(xml_text)
    except (ET.ParseError, TypeError, ValueError):
        return {"surface": "unknown", "proof": "invalid_xml"}

    nodes = list(root.iter("node"))
    header_nodes = [node for node in nodes if _node_in_task_header(node)]
    selected_tab = ""
    tab_prefixes = {
        "发现\n": "discover",
        "频道\n": "channel",
        "任务\n": "task",
        "我的\n": "my",
    }
    for node in nodes:
        if str(node.attrib.get("selected") or "").lower() != "true":
            continue
        description = str(node.attrib.get("content-desc") or "").strip()
        for prefix, tab_name in tab_prefixes.items():
            if description.startswith(prefix):
                selected_tab = tab_name
                break
        if selected_tab:
            break
    ready = any(
        str(node.attrib.get("content-desc") or "").strip() == "签到"
        and (
            str(node.attrib.get("clickable") or "").lower() == "true"
            or str(node.attrib.get("class") or "").endswith("Button")
        )
        for node in header_nodes
    )
    coin_label = any(
        str(node.attrib.get("content-desc") or "").strip() == "金币"
        for node in header_nodes
    )
    coin_value = any(
        re.fullmatch(
            r"\d+", str(node.attrib.get("content-desc") or "").strip()
        )
        is not None
        for node in header_nodes
    )

    if ready and not coin_label:
        return {
            "surface": "task_ready",
            "proof": "accessibility_signin_button",
            "selected_tab": selected_tab,
        }
    if coin_label and coin_value and not ready:
        return {
            "surface": "task_signed",
            "proof": "accessibility_coin_balance",
            "selected_tab": selected_tab,
        }
    return {
        "surface": "unknown",
        "proof": "ambiguous_task_header",
        "selected_tab": selected_tab,
    }


def _read_task_accessibility(adb: AdbClient) -> dict[str, Any]:
    """抓取一次语义树；失败只返回证据，不在导航状态机内直接抛错。"""

    dumped = adb.run(
        "shell",
        "uiautomator",
        "dump",
        TASK_UI_HIERARCHY_PATH,
        timeout=25,
        check=False,
        sensitive=True,
    )
    if dumped.returncode != 0:
        return {"surface": "unknown", "proof": "dump_failed", "selected_tab": ""}
    hierarchy = adb.run(
        "shell",
        "cat",
        TASK_UI_HIERARCHY_PATH,
        timeout=15,
        check=False,
        sensitive=True,
    )
    if hierarchy.returncode != 0:
        return {"surface": "unknown", "proof": "read_failed", "selected_tab": ""}
    return _task_surface_from_accessibility(hierarchy.stdout)


def _wait_task_semantic_surface(
    adb: AdbClient,
    *,
    timeout: float = 12,
    interval: float = 1.0,
) -> tuple[str, dict[str, Any]]:
    """读取任务页语义树；没有直接证据时 fail-closed，不把历史勾选算成功。"""

    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {"surface": "unknown", "proof": "not_read"}
    while time.monotonic() < deadline:
        last = _read_task_accessibility(adb)
        surface = str(last.get("surface") or "unknown")
        if surface in {"task_ready", "task_signed"}:
            adb.logger.info(
                "任务状态语义复核 surface=%s proof=%s",
                surface,
                last.get("proof"),
            )
            return surface, last
        time.sleep(interval)
    raise ScriptError(
        "任务页缺少可核实的今日签到语义证据；"
        f"last={last.get('proof', 'unknown')}"
    )


def _check_environment(adb: AdbClient) -> dict[str, Any]:
    state = adb.run("get-state").stdout.strip()
    boot = adb.run("shell", "getprop", "sys.boot_completed").stdout.strip()
    size = adb.run("shell", "wm", "size").stdout
    density = adb.run("shell", "wm", "density").stdout
    api = adb.run("shell", "getprop", "ro.build.version.sdk").stdout.strip()
    package = adb.run("shell", "dumpsys", "package", PACKAGE, timeout=35).stdout
    mismatches: list[str] = []
    if state != "device":
        mismatches.append(f"state={state}")
    if boot != "1":
        mismatches.append(f"boot={boot}")
    if f"{LOCKED_WIDTH}x{LOCKED_HEIGHT}" not in size:
        mismatches.append("wm_size")
    if str(LOCKED_DENSITY) not in density:
        mismatches.append("density")
    if api != LOCKED_API:
        mismatches.append(f"api={api}")
    if f"versionName={LOCKED_VERSION}" not in package:
        mismatches.append("version")
    if mismatches:
        raise ScriptError("环境合同不匹配: " + ",".join(mismatches))
    return {
        "serial": LOCKED_SERIAL,
        "size": f"{LOCKED_WIDTH}x{LOCKED_HEIGHT}",
        "density": LOCKED_DENSITY,
        "api": int(LOCKED_API),
        "version": LOCKED_VERSION,
    }


def _launch_app(adb: AdbClient, *, force: bool = False) -> None:
    activities = adb.run("shell", "dumpsys", "activity", "activities", timeout=25).stdout
    resumed = next(
        (line for line in activities.splitlines() if "topResumedActivity=" in line),
        "",
    )
    if not force and PACKAGE in resumed and (
        MAIN_ACTIVITY in resumed or SPLASH_ACTIVITY in resumed
    ):
        # 专用模拟器保留 App 进程。不要每天 force-stop：这个 arm64 App 在 x86
        # NDK translation 下冷初始化约 90 秒，还会让 owner 多用户会话一起抖动。
        return

    command = ["shell", "am", "start"]
    if force:
        # ``-S`` 先停止目标包再启动，绕过 pm clear 后短暂残留的 Activity 记录。
        command.append("-S")
    command.extend(
        ["--user", "current", "-n", f"{PACKAGE}/{SPLASH_ACTIVITY}"]
    )
    adb.run(*command, timeout=30)
    # ``am start -W`` 会一直等 Activity 完成启动。pm clear 后的 arm64 App 在
    # x86 NDK translation 下可能初始化 160 秒以上，命令超时并不表示启动失败。
    # 改为非阻塞启动，把完整就绪判断统一交给 _dismiss_announcements 的截图状态机。
    time.sleep(2.5)


def _dismiss_announcements(
    adb: AdbClient,
    worker: OcrWorker,
    *,
    timeout: int = 240,
    stale_surface: str | None = None,
    stale_grace_sec: float = 15.0,
) -> int:
    closed = 0
    started_at = time.monotonic()
    deadline = started_at + timeout
    next_progress_log = started_at + 30
    next_semantic_probe = started_at + 5
    last_logged_surface = ""
    stale_logged = False
    while time.monotonic() < deadline:
        png = adb.screenshot()
        evidence = worker.request("ui", png)
        surface = str(evidence.get("surface"))
        if surface != last_logged_surface:
            _log_ui_evidence(adb, "app_ready", evidence)
            last_logged_surface = surface
        elapsed = time.monotonic() - started_at
        if (
            stale_surface
            and surface == stale_surface
            and elapsed < stale_grace_sec
        ):
            if not stale_logged:
                adb.logger.info(
                    "自动换绑：忽略清数据后短暂残留的旧界面 surface=%s",
                    surface,
                )
                stale_logged = True
            time.sleep(1.5)
            continue
        if surface == "announcement":
            if closed >= 9:
                raise ScriptError("公告关闭连续重试超过安全上限")
            _close_announcement(adb, closed)
            closed += 1
            time.sleep(2.5)
            continue
        if surface != "unknown":
            return closed
        now = time.monotonic()
        if now >= next_semantic_probe:
            semantic = _read_task_accessibility(adb)
            selected_tab = str(semantic.get("selected_tab") or "")
            if selected_tab in ROOT_NAV_TABS:
                adb.logger.info(
                    "App 已加载，语义底栏确认 selected_tab=%s proof=%s",
                    selected_tab,
                    semantic.get("proof"),
                )
                return closed
            next_semantic_probe = now + 8
        if now >= next_progress_log:
            adb.logger.info(
                "App 冷启动仍在加载，已等待 %d 秒",
                int(now - started_at),
            )
            next_progress_log += 30
        time.sleep(1.5)
    raise ScriptError(f"App 启动后 {timeout} 秒仍处于未知界面")


def _log_ui_evidence(adb: AdbClient, phase: str, evidence: dict[str, Any]) -> None:
    """只记录不含账号/截图的分类证据，便于直接从管家日志复盘。"""

    logger = getattr(adb, "logger", None)
    if logger is None:
        return
    surface = str(evidence.get("surface") or "unknown")
    confidence = evidence.get("confidence")
    scores = evidence.get("scores")
    logger.info(
        "UI 状态 phase=%s surface=%s confidence=%s scores=%s",
        phase,
        surface,
        f"{float(confidence):.3f}" if isinstance(confidence, (int, float)) else "-",
        json.dumps(scores, ensure_ascii=True, sort_keys=True)
        if isinstance(scores, dict)
        else "-",
    )


def _close_announcement(adb: AdbClient, attempt: int) -> None:
    """点击公告的“不再显示”；连续丢触摸时每第三次用 BACK 作安全兜底。"""

    if (attempt + 1) % 3 == 0:
        adb.logger.info("公告关闭按钮连续丢触摸，改用 BACK 关闭当前弹窗")
        adb.key("4")
    else:
        adb.tap(587, 1018)


def _navigate_my(
    adb: AdbClient, worker: OcrWorker
) -> tuple[str, dict[str, Any], bytes]:
    """从已知安全界面有界恢复到“我的”，容忍延迟公告和一次丢触摸。"""

    deadline = time.monotonic() + 75
    back_presses = 0
    announcement_streak = 0
    nav_taps = 0
    next_semantic_probe = time.monotonic()
    last_surface = "unknown"
    last_logged_surface = ""
    while time.monotonic() < deadline:
        png = adb.screenshot()
        evidence = worker.request("ui", png)
        surface = str(evidence.get("surface"))
        last_surface = surface
        if surface != last_logged_surface:
            _log_ui_evidence(adb, "navigate_my", evidence)
            last_logged_surface = surface
        if surface in {"my_logged_in", "my_logged_out"}:
            return surface, evidence, png

        if surface in {"captcha", "login_form"} and back_presses < 3:
            adb.key("4")
            back_presses += 1
            time.sleep(1.5)
            continue

        # 公告有时在首页已经出现后才延迟弹出；原流程只在启动阶段关闭一次，
        # 导航阶段会把“我的”点击落在遮罩层后。这里只点击已被分类器确认的
        # 公告关闭坐标，并给触摸丢失留下重试预算。
        if surface == "announcement":
            if announcement_streak >= 9:
                raise ScriptError("导航期间公告关闭重试超过安全上限")
            _close_announcement(adb, announcement_streak)
            announcement_streak += 1
            time.sleep(2.5)
            continue
        announcement_streak = 0

        if surface == "task_success_dialog":
            adb.key("4")
            back_presses += 1
            time.sleep(1.5)
            continue

        # 只在确认底栏可见的固定界面点击“我的”。Flutter 首次全冷启动时
        # 第一次点击偶尔被页面初始化吞掉，因此允许有界重复。
        if surface in {"home", "task_ready", "task_signed", "task_page"}:
            if nav_taps >= 6:
                raise ScriptError("“我的”底栏点击重试超过安全上限")
            adb.tap(630, 1210)
            nav_taps += 1
            time.sleep(2.5)
            continue

        now = time.monotonic()
        if surface == "unknown" and now >= next_semantic_probe:
            semantic = _read_task_accessibility(adb)
            selected_tab = str(semantic.get("selected_tab") or "")
            next_semantic_probe = now + 5
            if selected_tab in ROOT_NAV_TABS - {"my"}:
                if nav_taps >= 6:
                    raise ScriptError("“我的”底栏语义导航重试超过安全上限")
                adb.logger.info(
                    "视觉状态 unknown，语义底栏确认 selected_tab=%s，转到“我的”",
                    selected_tab,
                )
                adb.tap(630, 1210)
                nav_taps += 1
                time.sleep(2.5)
                continue

        time.sleep(1.5)

    raise ScriptError(
        "等待界面超时 expected=['my_logged_in', 'my_logged_out'] "
        f"last={last_surface}"
    )


def _ensure_email_form(adb: AdbClient, worker: OcrWorker) -> None:
    adb.tap(235, 210)
    _, evidence, _ = _wait_surface(adb, worker, {"login_form"}, timeout=10)
    mode = str(evidence.get("login_mode"))
    # 初次分类若恰好落在 unknown，最多需要“邮箱→手机→邮箱”两次切换才能
    # 回到确定状态；第三轮只做终态检查，不会多点一次。
    for attempt in range(3):
        if mode == "email":
            return
        if attempt == 2:
            break
        adb.tap(150, 746)
        time.sleep(1.2)
        _, evidence, _ = _wait_surface(adb, worker, {"login_form"}, timeout=5)
        mode = str(evidence.get("login_mode"))
    raise ScriptError("无法把登录表单切换为邮箱模式")


def _fill_credentials(adb: AdbClient, account: str, password: str) -> None:
    adb.tap(250, 423)
    time.sleep(0.5)
    adb.select_all()
    adb.type_text(account)
    adb.key("4")
    time.sleep(1.5)
    adb.tap(250, 520)
    time.sleep(0.5)
    adb.select_all()
    adb.type_text(password)
    adb.key("4")
    time.sleep(1.5)


def _open_captcha(adb: AdbClient, worker: OcrWorker) -> bytes:
    adb.tap(360, 663)
    _, _, png = _wait_surface(adb, worker, {"captcha"}, timeout=18)
    return png


def _wait_changed_captcha(
    adb: AdbClient,
    worker: OcrWorker,
    previous_fingerprint: str,
    *,
    timeout: float = 10,
) -> tuple[bytes | None, str | None]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        png = adb.screenshot()
        ui = worker.request("ui", png)
        surface = str(ui.get("surface"))
        if surface == "captcha":
            fingerprint = str(ui.get("formula_fingerprint") or "")
            if fingerprint and fingerprint != previous_fingerprint:
                return png, fingerprint
        elif surface == "login_form":
            return None, None
        time.sleep(0.8)
    return None, None


def _wait_login_outcome(
    adb: AdbClient,
    worker: OcrWorker,
    *,
    timeout: float = 60,
) -> tuple[str, dict[str, Any]]:
    """等待登录请求结束；灰色按钮表示请求仍在处理中。"""

    deadline = time.monotonic() + timeout
    saw_pending_form = False
    pending_since: float | None = None
    pending_back_probed = False
    home_tapped = False
    last: dict[str, Any] = {"surface": "unknown"}
    while time.monotonic() < deadline:
        last = worker.request("ui", adb.screenshot())
        surface = str(last.get("surface"))
        if surface in {"my_logged_in", "my_logged_out"}:
            return surface, last
        if surface == "home" and not home_tapped:
            adb.tap(630, 1210)
            home_tapped = True
            time.sleep(1.5)
            continue
        if surface == "login_form":
            if not bool(last.get("login_button_active")):
                saw_pending_form = True
                if pending_since is None:
                    pending_since = time.monotonic()
                elif (
                    not pending_back_probed
                    and time.monotonic() - pending_since >= 12
                ):
                    # 实测成功登录后该版本偶尔仍把灰色旧表单留在返回栈顶；
                    # 等请求 12 秒后按一次返回，再以“我的”页真实账户头判断。
                    adb.key("4")
                    pending_back_probed = True
                    time.sleep(2.0)
                    continue
            elif saw_pending_form:
                return surface, last
            else:
                # 请求可能在第一次截图前已经快速失败并恢复按钮。
                return surface, last
        time.sleep(1.5)
    if str(last.get("surface")) == "login_form" and not bool(
        last.get("login_button_active")
    ):
        return "login_pending_timeout", last
    return str(last.get("surface")), last


def _login_with_captcha(
    adb: AdbClient,
    worker: OcrWorker,
    config: dict[str, Any],
    logger: logging.Logger,
) -> dict[str, Any]:
    account = _normalized_account(config)
    password = _require_login_password(config)

    min_confidence = _bounded_float(config, "captcha_min_confidence", 0.72, 0.5, 0.99)
    max_images = _bounded_int(config, "captcha_max_images", 30, 4, 30)
    max_submissions = _bounded_int(config, "captcha_max_submissions", 2, 1, 3)
    refresh_interval = _bounded_int(
        config, "captcha_refresh_interval_sec", 12, 5, 30
    )

    _ensure_email_form(adb, worker)
    _fill_credentials(adb, account, password)
    png = _open_captcha(adb, worker)
    submissions = 0
    refreshes = 0
    modal_rounds = 1

    image_index = 0
    stale_retries = 0
    while image_index < max_images:
        image_index += 1
        solved = worker.request(
            "captcha",
            png,
            min_confidence=min_confidence,
        )
        fingerprint = str(solved.get("formula_fingerprint") or "")
        if solved.get("accepted"):
            answer = str(solved.get("answer") or "")
            expression = str(solved.get("expression") or "")
            confidence = float(solved.get("confidence") or 0.0)
            logger.info(
                "验证码高置信命中：题型=%s confidence=%.3f（第 %d 张）",
                "乘法",
                confidence,
                image_index,
            )
            adb.tap(262, 700)
            time.sleep(0.4)
            adb.select_all()
            adb.type_text(answer)
            time.sleep(0.5)
            before_submit = adb.screenshot()
            current = worker.request("fingerprint", before_submit)
            if str(current.get("formula_fingerprint") or "") != fingerprint:
                logger.warning("输入答案期间验证码已刷新，放弃本次提交")
                stale_retries += 1
                if stale_retries > 3:
                    raise ScriptError("验证码连续在输入期间刷新，已停止本轮登录")
                # 这张题已经在提交前失效，不占用户配置的有效图片预算；让当前
                # 新图继续使用同一个序号，避免恰好在第 max_images 张命中时直接
                # 退出。旧答案会在下一次高置信命中时 select_all 覆盖。
                image_index -= 1
                png = before_submit
                continue
            adb.tap(523, 700)
            submissions += 1
            post_surface, _post = _wait_login_outcome(adb, worker, timeout=60)
            if post_surface == "my_logged_in":
                return {
                    "logged_in": True,
                    "captcha_images": image_index,
                    "captcha_refreshes": refreshes,
                    "captcha_submissions": submissions,
                    "modal_rounds": modal_rounds,
                    "captcha_stale_retries": stale_retries,
                    "solver_confidence": confidence,
                    "solver_expression": expression,
                }
            if submissions >= max_submissions:
                raise ScriptError("高置信验证码提交后仍未登录，已达到提交上限")
            if post_surface == "login_pending_timeout":
                raise ScriptError("验证码提交后登录请求 60 秒仍未完成")
            if post_surface != "login_form":
                raise ScriptError(f"验证码提交后界面未知: {post_surface}")
            logger.warning("验证码提交未登录；重新打开新验证码，不复用旧图")
            png = _open_captcha(adb, worker)
            modal_rounds += 1
            continue

        logger.info(
            "验证码低置信，刷新：reason=%s confidence=%.3f（第 %d 张）",
            solved.get("reason"),
            float(solved.get("confidence") or 0.0),
            image_index,
        )
        adb.tap(91, 701)
        refreshes += 1
        # 服务端对连续刷新有限频；过密会返回“获取问题过于频繁”并
        # 保留旧图。固定节流比快速重试更快获得新的可用题。
        time.sleep(refresh_interval)
        changed, _ = _wait_changed_captcha(adb, worker, fingerprint)
        if changed is not None:
            png = changed
            continue

        # 弹窗有时会在约 40 秒后自动关闭。字段仍在登录表单里，只重新点登录，
        # 不重输也不提交任何猜测答案。
        current_png = adb.screenshot()
        current_ui = worker.request("ui", current_png)
        current_surface = str(current_ui.get("surface"))
        if current_surface == "captcha":
            # 刷新按钮偶尔丢触摸或服务端返回同一张图。保留当前弹窗，下一轮
            # 重新判定并再次刷新；绝不把“未换图”误当成弹窗异常。
            logger.info("验证码刷新后仍是同一张图，下一轮重试刷新")
            png = current_png
            continue
        if current_surface != "login_form":
            raise ScriptError("刷新验证码后弹窗消失且未回到登录表单")
        png = _open_captcha(adb, worker)
        modal_rounds += 1

    raise ScriptError(
        f"连续查看 {max_images} 张验证码仍无高置信结果；未提交猜测答案"
    )


def _navigate_task(
    adb: AdbClient, worker: OcrWorker
) -> tuple[str, dict[str, Any], bytes]:
    """从已知安全界面有界进入任务中心，容忍延迟公告和丢触摸。"""

    deadline = time.monotonic() + 75
    announcement_streak = 0
    nav_taps = 0
    next_semantic_probe = 0.0
    last_surface = "unknown"
    last_logged_surface = ""
    while time.monotonic() < deadline:
        png = adb.screenshot()
        evidence = worker.request("ui", png)
        surface = str(evidence.get("surface"))
        last_surface = surface
        if surface != last_logged_surface:
            _log_ui_evidence(adb, "navigate_task", evidence)
            last_logged_surface = surface
        if surface in {
            "task_ready",
            "task_signed",
            "task_page",
            "task_success_dialog",
        }:
            return surface, evidence, png

        if surface == "announcement":
            if announcement_streak >= 9:
                raise ScriptError("任务导航期间公告关闭重试超过安全上限")
            _close_announcement(adb, announcement_streak)
            announcement_streak += 1
            time.sleep(2.5)
            continue
        announcement_streak = 0

        # 任务底栏在首页和已登录“我的”页都是固定安全坐标。
        # Flutter 页面初始化可能吞掉首次点击，因此只在这两种已知
        # 界面有界重试，不在 unknown/登录表单上盲点。
        if surface in {"home", "my_logged_in"}:
            if nav_taps >= 6:
                raise ScriptError("“任务”底栏点击重试超过安全上限")
            adb.tap(450, 1210)
            nav_taps += 1
            time.sleep(2.5)
            continue

        if surface == "my_logged_out":
            raise ScriptError("进入任务中心前登录态已失效")

        # 管家 run 104 复现过一次：点击“任务”后视觉帧进入 unknown，旧状态机
        # 因而不再重试，最终空等 75 秒。unknown 时不盲点；只有 accessibility
        # 明确仍在任一非任务底栏页才重试，若任务页语义已出现则直接进入后续复核。
        now = time.monotonic()
        if surface == "unknown" and nav_taps > 0 and now >= next_semantic_probe:
            semantic = _read_task_accessibility(adb)
            next_semantic_probe = now + 5
            semantic_surface = str(semantic.get("surface") or "unknown")
            if semantic_surface in {"task_ready", "task_signed"}:
                recovered = dict(evidence)
                recovered.update(
                    {
                        "surface": semantic_surface,
                        "semantic_proof": semantic.get("proof"),
                    }
                )
                adb.logger.info(
                    "任务视觉 unknown，已由语义树恢复 surface=%s proof=%s",
                    semantic_surface,
                    semantic.get("proof"),
                )
                return semantic_surface, recovered, png
            selected_tab = str(semantic.get("selected_tab") or "")
            if selected_tab in {"discover", "channel", "my"}:
                if nav_taps >= 6:
                    raise ScriptError("“任务”底栏点击重试超过安全上限")
                adb.logger.info(
                    "任务底栏触摸未到达目标，语义树仍选中 tab=%s；安全重试",
                    selected_tab,
                )
                adb.tap(450, 1210)
                nav_taps += 1
                time.sleep(2.5)
                continue

        time.sleep(1.5)

    raise ScriptError(
        "等待界面超时 expected=['task_ready', 'task_signed', 'task_page', "
        f"'task_success_dialog'] last={last_surface}"
    )


def _perform_daily_checkin(adb: AdbClient, worker: OcrWorker) -> dict[str, Any]:
    """进入任务中心，以视觉定位、语义树定状态，幂等执行一次签到。"""

    surface, evidence, _ = _navigate_task(adb, worker)
    if surface == "task_success_dialog":
        adb.key("4")
        surface, evidence, _ = _wait_surface(
            adb, worker, {"task_signed", "task_page"}, timeout=8
        )
    visual_surface = surface
    surface, semantic_evidence = _wait_task_semantic_surface(adb)
    if surface != visual_surface:
        adb.logger.info(
            "任务视觉状态由语义证据纠正 visual=%s semantic=%s",
            visual_surface,
            surface,
        )
    if surface == "task_signed":
        return {
            "checked_in": True,
            "already_checked_in": True,
            "checkin_confidence": evidence.get("confidence"),
            "checkin_proof": semantic_evidence.get("proof"),
        }

    # 只有 accessibility 明确暴露顶部“签到”按钮才点击每日唯一动作；
    # 历史奖励勾选、未知页面或单一视觉模板都不会触发。
    adb.tap(360, 247)
    surface, evidence, _ = _wait_surface(
        adb,
        worker,
        {"task_success_dialog", "task_signed", "task_page"},
        timeout=60,
    )
    success_dialog_seen = surface == "task_success_dialog"
    if success_dialog_seen:
        adb.key("4")
        surface, evidence, _ = _wait_surface(
            adb, worker, {"task_signed", "task_page"}, timeout=10
        )
    visual_surface = surface
    surface, semantic_evidence = _wait_task_semantic_surface(adb)
    if surface != "task_signed":
        raise ScriptError(
            "签到点击后未得到今日已签到语义证据: "
            f"visual={visual_surface}, semantic={surface}"
        )
    return {
        "checked_in": True,
        "already_checked_in": False,
        "success_dialog_seen": success_dialog_seen,
        "checkin_confidence": evidence.get("confidence"),
        "checkin_proof": semantic_evidence.get("proof"),
    }


def _build_lifecycle(
    config: dict[str, Any], adb_path: str, serial: str, logger: logging.Logger
) -> tuple[EmulatorLifecycle, int]:
    avd_name = str(config.get("emulator_avd") or "poc34").strip()
    start_timeout = _bounded_int(
        config, "emulator_start_timeout_sec", 300, 60, 600
    )
    shutdown_timeout = _bounded_int(
        config, "emulator_shutdown_timeout_sec", 60, 10, 120
    )
    lock_timeout = _bounded_int(
        config, "emulator_lock_timeout_sec", 600, 0, 900
    )
    lifecycle = EmulatorLifecycle(
        adb_path=adb_path,
        serial=serial,
        avd_name=avd_name,
        logger=logger,
        start_timeout=start_timeout,
        shutdown_timeout=shutdown_timeout,
        manage=bool(config.get("manage_emulator", True)),
        stop_after_run=bool(config.get("stop_emulator_after_run", True)),
    )
    return lifecycle, lock_timeout


def run(config: dict[str, Any], context: Any) -> RunResult:
    logger: logging.Logger = context.logger
    if context.run_id == 0 and context.instance_id == 0:
        return RunResult(success=True, message="dry-run OK")

    random_delay = _bounded_int(config, "random_delay_sec", 0, 0, 1800)
    if random_delay:
        import random

        delay = random.randint(0, random_delay)
        logger.info("随机延迟 %d 秒", delay)
        time.sleep(delay)

    adb_path = str(config.get("adb_path") or "/opt/android-sdk/platform-tools/adb")
    serial = str(config.get("adb_serial") or LOCKED_SERIAL)
    adb = AdbClient(adb_path, serial, logger)
    lifecycle: EmulatorLifecycle | None = None
    account_rebind_attempted = False

    try:
        account = _normalized_account(config)
        python, solver, assets = ensure_ocr_runtime(config, context, logger)
        lifecycle, lock_timeout = _build_lifecycle(config, adb_path, serial, logger)
        result: RunResult | None = None
        with _sigterm_cleanup_guard(), ExclusiveFileLock(
            LOCK_PATH, lock_timeout, logger
        ):
            ready = False
            try:
                lifecycle.ensure_ready()
                ready = True
                environment = _check_environment(adb)
                expected_binding = _expected_binding(account, lifecycle.avd_name)
                binding = _read_account_binding(adb)
                rebind_required = False
                if binding is not None:
                    _validate_binding_container(binding, expected_binding)
                    rebind_required = not _binding_matches_account(
                        binding, expected_binding
                    )
                    if rebind_required:
                        if not bool(config.get("auto_rebind_account", True)):
                            _validate_account_binding(binding, expected_binding)
                        _require_login_password(config)

                with OcrWorker(python, solver, assets) as worker:
                    _launch_app(adb)
                    app_ready_timeout = _bounded_int(
                        config, "app_ready_timeout_sec", 240, 120, 480
                    )
                    closed = _dismiss_announcements(
                        adb, worker, timeout=app_ready_timeout
                    )
                    surface, login_evidence, my_png = _navigate_my(adb, worker)
                    if rebind_required:
                        if surface == "my_logged_in":
                            old_signature = _profile_signature(worker, my_png)
                            _verify_profile_signature(binding, old_signature)
                        logger.warning(
                            "检测到管家下发的账号发生变化；"
                            "正在清理旧 App 会话并执行一次性自动换绑"
                        )
                        account_rebind_attempted = True
                        _reset_app_for_account_rebind(adb)
                        binding = None
                        _launch_app(adb, force=True)
                        closed += _dismiss_announcements(
                            adb,
                            worker,
                            timeout=app_ready_timeout,
                            stale_surface=surface,
                        )
                        surface, login_evidence, my_png = _navigate_my(
                            adb, worker
                        )
                        if surface != "my_logged_out":
                            raise ScriptError(
                                "清理旧账户后 App 仍不是未登录状态，已停止换绑"
                            )

                    already_logged_in = surface == "my_logged_in"
                    login_result: dict[str, Any] = {}
                    account_rebound = False
                    if already_logged_in:
                        if binding is None:
                            raise ScriptError(
                                "当前 AVD 已登录但没有账户绑定标记；"
                                "需先由管理员核实并完成一次性迁移"
                            )
                        signature = _profile_signature(worker, my_png)
                        _verify_profile_signature(binding, signature)
                        login_result["login_confidence"] = login_evidence.get(
                            "confidence"
                        )
                    else:
                        login_result = _login_with_captcha(
                            adb, worker, config, logger
                        )
                        _, _, my_png = _wait_surface(
                            adb, worker, {"my_logged_in"}, timeout=12
                        )
                        signature = _profile_signature(worker, my_png)
                        if binding is None:
                            binding = _write_account_binding(
                                adb,
                                context,
                                expected_binding,
                                signature,
                            )
                            logger.info("已建立 AVD、账号与昵称字形三重绑定")
                            if rebind_required:
                                account_rebound = True
                                logger.info("管家下发的新账号已完成自动换绑")
                        else:
                            _verify_profile_signature(binding, signature)

                    checkin_result = _perform_daily_checkin(adb, worker)
                    already_checked_in = bool(
                        checkin_result.get("already_checked_in")
                    )
                    result = RunResult(
                        success=True,
                        message=(
                            "动漫共和国今日已签到"
                            if already_checked_in
                            else "动漫共和国签到成功"
                        ),
                        data={
                            "action": "daily_checkin",
                            "already_logged_in": already_logged_in,
                            "announcements_closed": closed,
                            "environment": environment,
                            "account_binding_verified": True,
                            "account_rebound": account_rebound,
                            "checkin_action_enabled": True,
                            **login_result,
                            **checkin_result,
                        },
                    )
            finally:
                if ready or lifecycle.started_by_run:
                    lifecycle.stop()
        if result is None:
            raise ScriptError("签到流程未生成结果")
        result.data["emulator"] = lifecycle.report()
        return result
    except (ScriptError, EmulatorLifecycleError) as exc:
        logger.error("动漫共和国登录保活失败：%s", exc)
        data: dict[str, Any] = {
            "action": "daily_checkin",
            "error_class": type(exc).__name__,
            "account_rebind_attempted": account_rebind_attempted,
        }
        if lifecycle is not None:
            data["emulator"] = lifecycle.report()
        return RunResult(
            success=False,
            message=str(exc)[:512],
            data=data,
        )
    except Exception as exc:  # 平台边界：未知异常仍返回结构化 failure
        logger.exception("动漫共和国登录保活出现未预期异常")
        data = {
            "action": "daily_checkin",
            "error_class": type(exc).__name__,
            "account_rebind_attempted": account_rebind_attempted,
        }
        if lifecycle is not None:
            data["emulator"] = lifecycle.report()
        return RunResult(
            success=False,
            message=f"{type(exc).__name__}: {exc}"[:512],
            data=data,
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    class _Context:
        run_id = 1
        instance_id = 1
        logger = logging.getLogger("dmgongheguo")
        script_dir = str(Path(__file__).resolve().parent)
        data_dir = os.environ.get(
            "DMGH_DATA_DIR", str(Path(__file__).resolve().parent / "_local_data")
        )

    result = run({}, _Context())
    print(json.dumps(result.__dict__, ensure_ascii=False))
