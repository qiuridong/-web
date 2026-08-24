"""Android Emulator 的串行、按需启动和可靠收尾。

生产节点通过 ``dmgongheguo-emulator@.service`` 托管 QEMU。本模块只使用
Python 标准库：先持有跨进程文件锁，再启动指定 AVD，等待 ADB 与 Android
完成启动；任务结束后无论成功或失败都停止 Emulator。
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path
from typing import BinaryIO, Any

LOCKED_SERIAL = "emulator-6554"
LOCK_PATH = Path("/run/lock/dmgongheguo-emulator-6554.lock")
SYSTEMCTL_PATH = "/usr/bin/systemctl"
UNIT_PREFIX = "dmgongheguo-emulator"
_AVD_NAME_RE = re.compile(r"[A-Za-z0-9._-]{1,64}")


class EmulatorLifecycleError(RuntimeError):
    """Emulator 互斥、启动、身份校验或关闭失败。"""


class ExclusiveFileLock:
    """进程退出时由内核自动释放的跨平台独占文件锁。"""

    def __init__(self, path: Path, timeout: float, logger: Any) -> None:
        self.path = path
        self.timeout = timeout
        self.logger = logger
        self._file: BinaryIO | None = None

    def _try_acquire(self, handle: BinaryIO) -> bool:
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                if handle.read(1) == b"":
                    handle.seek(0)
                    handle.write(b"\0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError):
            return False
        return True

    def acquire(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            handle = self.path.open("a+b")
        except OSError as exc:
            raise EmulatorLifecycleError(
                f"无法创建 Emulator 全局锁: {type(exc).__name__}"
            ) from exc

        deadline = time.monotonic() + self.timeout
        while not self._try_acquire(handle):
            if time.monotonic() >= deadline:
                handle.close()
                raise EmulatorLifecycleError(
                    f"等待 Emulator 全局锁超过 {self.timeout:.0f} 秒；"
                    "已有另一个 Android 任务正在运行"
                )
            time.sleep(0.5)
        self._file = handle
        self.logger.info("已获取 Emulator 全局串行锁")

    def release(self) -> None:
        handle = self._file
        self._file = None
        if handle is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()

    def __enter__(self) -> ExclusiveFileLock:
        self.acquire()
        return self

    def __exit__(self, *_: object) -> None:
        self.release()


class EmulatorLifecycle:
    """管理固定 ADB 端口上的一个 systemd Emulator 实例。"""

    def __init__(
        self,
        *,
        adb_path: str,
        serial: str,
        avd_name: str,
        logger: Any,
        start_timeout: int,
        shutdown_timeout: int,
        manage: bool,
        stop_after_run: bool,
        systemctl_path: str = SYSTEMCTL_PATH,
    ) -> None:
        if serial != LOCKED_SERIAL:
            raise EmulatorLifecycleError(f"生命周期只允许设备 {LOCKED_SERIAL}")
        if _AVD_NAME_RE.fullmatch(avd_name) is None:
            raise EmulatorLifecycleError("emulator_avd 只能包含字母、数字、点、横线和下划线")
        if stop_after_run and not manage:
            raise EmulatorLifecycleError(
                "stop_emulator_after_run=true 要求 manage_emulator=true"
            )
        self.adb_path = adb_path
        self.serial = serial
        self.avd_name = avd_name
        self.logger = logger
        self.start_timeout = start_timeout
        self.shutdown_timeout = shutdown_timeout
        self.manage = manage
        self.stop_after_run = stop_after_run
        self.systemctl_path = systemctl_path
        self.unit = f"{UNIT_PREFIX}@{avd_name}.service"
        self.was_running = False
        self.started_by_run = False
        self.stopped = False
        self.boot_duration_ms = 0
        self.shutdown_duration_ms = 0

    def _run(
        self,
        command: list[str],
        *,
        timeout: float,
        check: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        try:
            result = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
        except (FileNotFoundError, PermissionError, subprocess.TimeoutExpired) as exc:
            raise EmulatorLifecycleError(
                f"命令执行失败 {Path(command[0]).name}: {type(exc).__name__}"
            ) from exc
        if check and result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()[-300:]
            raise EmulatorLifecycleError(
                f"{Path(command[0]).name} exit={result.returncode}: {detail}"
            )
        return result

    def _adb(
        self,
        *args: str,
        timeout: float = 10,
        check: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        return self._run(
            [self.adb_path, "-s", self.serial, *args],
            timeout=timeout,
            check=check,
        )

    def _systemctl(
        self,
        *args: str,
        timeout: float = 30,
        check: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        return self._run(
            [self.systemctl_path, *args],
            timeout=timeout,
            check=check,
        )

    def _device_state(self) -> str:
        result = self._adb("get-state", timeout=6, check=False)
        if result.returncode != 0:
            return "absent"
        return result.stdout.strip() or "unknown"

    def _unit_active(self) -> bool:
        result = self._systemctl("is-active", "--quiet", self.unit, timeout=8)
        return result.returncode == 0

    def _verify_unit_loaded(self) -> None:
        result = self._systemctl(
            "show",
            self.unit,
            "--property=LoadState",
            "--value",
            timeout=10,
            check=True,
        )
        if result.stdout.strip() != "loaded":
            raise EmulatorLifecycleError(
                f"systemd 单元 {self.unit} 未安装；请先安装模板服务"
            )

    def _actual_avd_name(self) -> str:
        result = self._adb("emu", "avd", "name", timeout=10, check=True)
        values = [
            line.strip()
            for line in result.stdout.splitlines()
            if line.strip() and line.strip() != "OK"
        ]
        return values[0] if values else ""

    def _wait_ready(self) -> None:
        deadline = time.monotonic() + self.start_timeout
        last_state = "absent"
        last_boot = ""
        while time.monotonic() < deadline:
            last_state = self._device_state()
            if last_state == "device":
                actual_avd = self._actual_avd_name()
                if actual_avd != self.avd_name:
                    raise EmulatorLifecycleError(
                        f"ADB {self.serial} 实际 AVD={actual_avd!r}，"
                        f"期望 {self.avd_name!r}"
                    )
                boot = self._adb(
                    "shell", "getprop", "sys.boot_completed", timeout=8
                )
                last_boot = boot.stdout.strip() if boot.returncode == 0 else ""
                if last_boot == "1":
                    self._adb(
                        "shell", "input", "keyevent", "82", timeout=8, check=False
                    )
                    return
            if self.started_by_run and not self._unit_active():
                status = self._systemctl(
                    "status", self.unit, "--no-pager", "-l", timeout=10
                )
                detail = (status.stdout or status.stderr).strip()[-500:]
                raise EmulatorLifecycleError(
                    f"Emulator 在完成启动前退出: {detail}"
                )
            time.sleep(2)
        raise EmulatorLifecycleError(
            f"等待 Emulator 启动超过 {self.start_timeout} 秒："
            f"state={last_state}, boot={last_boot!r}"
        )

    def ensure_ready(self) -> dict[str, Any]:
        started_at = time.monotonic()
        state = self._device_state()
        self.was_running = state == "device"
        if state not in {"absent", "device"}:
            raise EmulatorLifecycleError(
                f"ADB {self.serial} 当前状态为 {state!r}，拒绝启动重复 Emulator"
            )
        if state == "absent":
            if not self.manage:
                raise EmulatorLifecycleError(
                    f"ADB 设备 {self.serial} 不在线，且 manage_emulator 已关闭"
                )
            self._verify_unit_loaded()
            self.logger.info("按需启动 Android Emulator：AVD=%s", self.avd_name)
            self._systemctl("start", self.unit, timeout=30, check=True)
            self.started_by_run = True
        else:
            self.logger.info("复用已在线 Android Emulator：AVD=%s", self.avd_name)
        self._wait_ready()
        self.boot_duration_ms = int((time.monotonic() - started_at) * 1000)
        self.logger.info(
            "Android Emulator 已就绪：AVD=%s，等待 %d ms",
            self.avd_name,
            self.boot_duration_ms,
        )
        return self.report()

    def stop(self) -> None:
        if not self.manage or not self.stop_after_run:
            return
        started_at = time.monotonic()
        self.logger.info("签到流程结束，正在关闭 Android Emulator")
        if self._device_state() == "device":
            self._adb("shell", "sync", timeout=20, check=False)
        if self._unit_active():
            result = self._systemctl(
                "stop",
                self.unit,
                timeout=self.shutdown_timeout + 10,
                check=False,
            )
            if result.returncode != 0:
                self.logger.warning("systemctl stop 失败，改用 ADB 优雅关闭")
        if self._device_state() == "device":
            self._adb("emu", "kill", timeout=10, check=False)

        deadline = time.monotonic() + self.shutdown_timeout
        while time.monotonic() < deadline:
            if self._device_state() == "absent" and not self._unit_active():
                self.stopped = True
                self.shutdown_duration_ms = int(
                    (time.monotonic() - started_at) * 1000
                )
                self.logger.info(
                    "Android Emulator 已关闭：耗时 %d ms",
                    self.shutdown_duration_ms,
                )
                return
            time.sleep(1)

        self._systemctl(
            "kill", "--kill-whom=all", "--signal=KILL", self.unit, timeout=10
        )
        self._systemctl("stop", self.unit, timeout=10)
        if self._device_state() != "absent":
            raise EmulatorLifecycleError(
                f"Android Emulator 在 {self.shutdown_timeout} 秒内未关闭"
            )
        self.stopped = True
        self.shutdown_duration_ms = int((time.monotonic() - started_at) * 1000)

    def report(self) -> dict[str, Any]:
        return {
            "managed": self.manage,
            "stop_after_run": self.stop_after_run,
            "avd_name": self.avd_name,
            "unit": self.unit,
            "was_running": self.was_running,
            "started_by_run": self.started_by_run,
            "boot_duration_ms": self.boot_duration_ms,
            "stopped": self.stopped,
            "shutdown_duration_ms": self.shutdown_duration_ms,
        }
