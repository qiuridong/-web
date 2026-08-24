"""动漫共和国 Android 登录保活与算术验证码离线回归。"""

from __future__ import annotations

import importlib.util
import logging
import subprocess
import sys
from contextlib import nullcontext
from dataclasses import dataclass, field
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = ROOT / "scripts" / "dmgongheguo"
MAIN_PATH = SCRIPT_DIR / "main.py"
SOLVER_PATH = SCRIPT_DIR / "helpers" / "captcha_solver.py"
MANIFEST_PATH = SCRIPT_DIR / "manifest.yaml"
ASSETS_DIR = SCRIPT_DIR / "assets"
CAPTCHA_FIXTURES = Path(__file__).parent / "fixtures" / "dmgongheguo_captcha"
UI_FIXTURES = Path(__file__).parent / "fixtures" / "dmgongheguo_ui"

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_main():
    return _load_module("dmgongheguo_main_under_test", MAIN_PATH)


def load_solver():
    pytest.importorskip("cv2", reason="验证码回归需要脚本独立 OCR 运行时")
    pytest.importorskip("ddddocr", reason="验证码回归需要脚本独立 OCR 运行时")
    pytest.importorskip("numpy", reason="验证码回归需要脚本独立 OCR 运行时")
    pytest.importorskip("PIL", reason="验证码回归需要脚本独立 OCR 运行时")
    return _load_module("dmgongheguo_solver_under_test", SOLVER_PATH)


@pytest.fixture(scope="module")
def solver_runtime():
    ddddocr = pytest.importorskip(
        "ddddocr", reason="验证码回归需要脚本独立 OCR 运行时"
    )
    solver = load_solver()
    return solver, ddddocr.DdddOcr(show_ad=False)


def _solve(solver_runtime, name: str):
    solver, engine = solver_runtime
    np = pytest.importorskip("numpy")
    image_module = pytest.importorskip("PIL.Image")
    with image_module.open(CAPTCHA_FIXTURES / name) as source:
        frame = np.asarray(source.convert("RGB"))
    return solver.solve_captcha(
        frame,
        assets_dir=ASSETS_DIR,
        engine=engine,
        min_confidence=0.72,
    )


@pytest.mark.parametrize(
    ("name", "expression", "answer"),
    [
        ("captcha-005.png", "5*9", "45"),
        ("captcha-014.png", "7*2", "14"),
        ("captcha-024.png", "4*2", "8"),
        ("captcha-027.png", "1*3", "3"),
        ("captcha-104.png", "3*9", "27"),
        ("captcha-111.png", "4*2", "8"),
        # 以下三张在模板库冻结后从 VPS 新抓, 是真正的 holdout。
        ("holdout-6x7.png", "6*7", "42"),
        ("holdout-4x8.png", "4*8", "32"),
        ("holdout-4x6.png", "4*6", "24"),
    ],
)
def test_high_confidence_multiplication_is_exact(
    solver_runtime, name: str, expression: str, answer: str
):
    result = _solve(solver_runtime, name)
    assert result["accepted"] is True
    assert result["expression"] == expression
    assert result["answer"] == answer
    assert result["confidence"] >= 0.72


@pytest.mark.parametrize(
    "name",
    [
        "captcha-011.png",  # +
        "captcha-018.png",  # division; 整行 OCR 会把它误读成 x, 局部模板必须拦住
        "captcha-021.png",  # +
        "captcha-100.png",  # +
        "captcha-101.png",  # +
        "captcha-106.png",  # -
        "captcha-108.png",  # ÷
        "captcha-109.png",  # minus; 错误 grammar 曾产生高乘法模板分
        "captcha-110.png",  # ÷
        "captcha-112.png",  # -
        "holdout-52minus22.png",
        "holdout-15plus6.png",
        "holdout-3plus16.png",
    ],
)
def test_non_multiplication_never_submits(solver_runtime, name: str):
    result = _solve(solver_runtime, name)
    assert result["accepted"] is False
    assert result.get("answer") is None


def test_ambiguous_stylized_one_fails_closed(solver_runtime):
    """真题 8x1 的数字 1 被 OCR 多通道读成 9 时, 宁可刷新也不提交 72。"""

    result = _solve(solver_runtime, "holdout-adversarial-8x1.png")
    assert result["accepted"] is False
    assert result["confidence"] < 0.72


def test_ui_classifier_uses_fixed_safe_surfaces():
    solver = load_solver()
    np = pytest.importorskip("numpy")
    image_module = pytest.importorskip("PIL.Image")

    expected = {
        "home.png": ("home", None),
        "my-logged-out.png": ("my_logged_out", None),
        "login-phone.png": ("login_form", "phone"),
        "login-email-dummy.png": ("login_form", "email"),
        "announcement.png": ("announcement", None),
        "captcha-dummy.png": ("captcha", None),
        "task-ready.png": ("task_ready", None),
        "task-signed.png": ("task_signed", None),
        "task-success-dialog.png": ("task_success_dialog", None),
    }
    for name, (surface, mode) in expected.items():
        with image_module.open(UI_FIXTURES / name) as source:
            frame = np.asarray(source.convert("RGB"))
        result = solver.inspect_ui(frame, ASSETS_DIR)
        assert result["surface"] == surface
        if mode is not None:
            assert result["login_mode"] == mode


def test_unknown_login_mode_can_recover_to_email(monkeypatch):
    main = load_main()

    class FakeAdb:
        def __init__(self):
            self.taps: list[tuple[int, int]] = []

        def tap(self, x: int, y: int) -> None:
            self.taps.append((x, y))

        def screenshot(self) -> bytes:
            return b"fixture"

    class FakeWorker:
        def __init__(self):
            self.responses = iter(
                [
                    {"surface": "login_form", "login_mode": "unknown"},
                    {"surface": "login_form", "login_mode": "phone"},
                    {"surface": "login_form", "login_mode": "email"},
                ]
            )

        def request(self, mode: str, image: bytes):
            assert mode == "ui" and image == b"fixture"
            return next(self.responses)

    monkeypatch.setattr(main.time, "sleep", lambda _: None)
    adb = FakeAdb()
    main._ensure_email_form(adb, FakeWorker())
    assert adb.taps == [(235, 210), (150, 746), (150, 746)]


def test_dry_run_short_circuits_before_adb_or_ocr():
    main = load_main()

    @dataclass
    class Context:
        run_id: int = 0
        instance_id: int = 0
        logger: logging.Logger = field(
            default_factory=lambda: logging.getLogger("dmgongheguo-test")
        )

    result = main.run({}, Context())
    assert result.success is True
    assert "dry-run" in result.message


def test_daily_checkin_is_idempotent_when_already_signed(monkeypatch):
    main = load_main()

    class FakeAdb:
        def __init__(self):
            self.taps: list[tuple[int, int]] = []

        def tap(self, x: int, y: int) -> None:
            self.taps.append((x, y))

        def screenshot(self) -> bytes:
            return b"fixture"

    class FakeWorker:
        def request(self, mode: str, image: bytes):
            return {"surface": "task_signed", "confidence": 0.99}

    monkeypatch.setattr(main.time, "sleep", lambda _: None)
    adb = FakeAdb()
    result = main._perform_daily_checkin(adb, FakeWorker())
    assert result["already_checked_in"] is True
    assert adb.taps == [(450, 1210)]


def test_daily_checkin_clicks_once_and_requires_postcondition(monkeypatch):
    main = load_main()

    class FakeAdb:
        def __init__(self):
            self.taps: list[tuple[int, int]] = []
            self.keys: list[str] = []

        def tap(self, x: int, y: int) -> None:
            self.taps.append((x, y))

        def key(self, value: str) -> None:
            self.keys.append(value)

        def screenshot(self) -> bytes:
            return b"fixture"

    class FakeWorker:
        def __init__(self):
            self.responses = iter(
                [
                    {"surface": "task_ready", "confidence": 0.99},
                    {"surface": "task_success_dialog", "confidence": 0.99},
                    {"surface": "task_signed", "confidence": 0.99},
                ]
            )

        def request(self, mode: str, image: bytes):
            return next(self.responses)

    monkeypatch.setattr(main.time, "sleep", lambda _: None)
    adb = FakeAdb()
    result = main._perform_daily_checkin(adb, FakeWorker())
    assert result["already_checked_in"] is False
    assert result["success_dialog_seen"] is True
    assert adb.taps == [(450, 1210), (360, 247)]
    assert adb.keys == ["4"]


def test_manifest_and_asset_contract_pass_backend_validation():
    from app.plugins.manifest import parse_manifest

    manifest = parse_manifest(MANIFEST_PATH)
    assert manifest.slug == "dmgongheguo"
    assert str(manifest.version) == "1.2.1"
    assert manifest.default_timeout_sec == 1200
    keys = [field.key for field in manifest.fields]
    assert keys[:2] == ["account", "password"]
    assert "auto_rebind_account" in keys
    assert "emulator_avd" in keys
    assert "manage_emulator" in keys
    assert "stop_emulator_after_run" in keys
    assert "app_ready_timeout_sec" in keys
    assert (ASSETS_DIR / "ui" / "my-logged-out-header.png").is_file()
    assert len(list((ASSETS_DIR / "operators" / "multiply").glob("*.png"))) >= 8
    assert len(list((ASSETS_DIR / "operators" / "other").glob("*.png"))) >= 8


def test_adb_serial_is_fail_closed():
    main = load_main()
    with pytest.raises(main.ScriptError, match="emulator-6554"):
        main.AdbClient("adb", "unexpected-device", logging.getLogger("test"))


def test_profile_signature_is_stable_and_changes_with_glyphs():
    solver = load_solver()
    np = pytest.importorskip("numpy")
    cv2 = pytest.importorskip("cv2")

    frame = np.full((1280, 720, 3), (36, 44, 61), dtype=np.uint8)
    cv2.rectangle(frame, (175, 160), (190, 188), (245, 245, 245), -1)
    cv2.rectangle(frame, (200, 164), (220, 188), (245, 245, 245), -1)
    first = solver.inspect_profile_identity(frame)
    second = solver.inspect_profile_identity(frame.copy())
    assert first["profile_signature"] == second["profile_signature"]
    assert first["policy"] == "nickname_glyph_sha256_v1"

    changed = frame.copy()
    cv2.rectangle(changed, (230, 155), (240, 188), (245, 245, 245), -1)
    third = solver.inspect_profile_identity(changed)
    assert first["profile_signature"] != third["profile_signature"]


def test_account_binding_rejects_different_account_or_avd():
    main = load_main()
    expected = main._expected_binding("first@example.com", "poc34")
    binding = {**expected, "profile_signature": "a" * 64}
    main._validate_account_binding(binding, expected)

    with pytest.raises(main.ScriptError, match="绑定不匹配"):
        main._validate_account_binding(
            binding,
            main._expected_binding("second@example.com", "poc34"),
        )
    with pytest.raises(main.ScriptError, match="绑定不匹配"):
        main._validate_account_binding(
            binding,
            main._expected_binding("first@example.com", "another-avd"),
        )
    assert "first@example.com" not in str(binding)


def test_account_change_is_distinct_from_avd_binding_corruption():
    main = load_main()
    old_expected = main._expected_binding("first@example.com", "poc34")
    binding = {**old_expected, "profile_signature": "a" * 64}
    new_expected = main._expected_binding("second@example.com", "poc34")

    main._validate_binding_container(binding, new_expected)
    assert main._binding_matches_account(binding, new_expected) is False

    wrong_avd = main._expected_binding("second@example.com", "other-avd")
    with pytest.raises(main.ScriptError, match="App/AVD"):
        main._validate_binding_container(binding, wrong_avd)


def test_account_rebind_reset_clears_app_data_marker_and_syncs():
    main = load_main()

    class FakeAdb:
        def __init__(self):
            self.calls: list[tuple[str, ...]] = []

        def run(self, *args, **_kwargs):
            self.calls.append(args)
            if args[:3] == ("shell", "pm", "clear"):
                return subprocess.CompletedProcess(args, 0, "Success\n", "")
            if args[:2] == ("shell", "cat"):
                return subprocess.CompletedProcess(
                    args, 1, "", "No such file or directory"
                )
            return subprocess.CompletedProcess(args, 0, "", "")

    adb = FakeAdb()
    main._reset_app_for_account_rebind(adb)

    assert (
        "shell",
        "am",
        "force-stop",
        main.PACKAGE,
    ) in adb.calls
    assert ("shell", "pm", "clear", main.PACKAGE) in adb.calls
    assert (
        "shell",
        "rm",
        "-f",
        main.ACCOUNT_BINDING_PATH,
    ) in adb.calls
    assert ("shell", "sync") in adb.calls


def test_account_rebind_reset_stops_if_pm_clear_fails():
    main = load_main()

    class FakeAdb:
        def run(self, *args, **_kwargs):
            if args[:3] == ("shell", "pm", "clear"):
                return subprocess.CompletedProcess(args, 1, "Failed\n", "")
            return subprocess.CompletedProcess(args, 0, "", "")

    with pytest.raises(main.ScriptError, match="清理旧 App 账户数据失败"):
        main._reset_app_for_account_rebind(FakeAdb())


def test_emulator_lifecycle_starts_expected_systemd_unit(monkeypatch):
    from helpers.emulator_lifecycle import EmulatorLifecycle

    lifecycle = EmulatorLifecycle(
        adb_path="/sdk/adb",
        serial="emulator-6554",
        avd_name="poc34",
        logger=logging.getLogger("test"),
        start_timeout=60,
        shutdown_timeout=5,
        manage=True,
        stop_after_run=True,
        systemctl_path="/bin/systemctl",
    )
    states = iter(["absent", "device"])
    systemctl_calls: list[tuple[str, ...]] = []
    adb_calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(lifecycle, "_device_state", lambda: next(states))
    monkeypatch.setattr(lifecycle, "_verify_unit_loaded", lambda: None)
    monkeypatch.setattr(lifecycle, "_actual_avd_name", lambda: "poc34")
    monkeypatch.setattr(lifecycle, "_unit_active", lambda: True)

    def fake_systemctl(*args, **_kwargs):
        systemctl_calls.append(args)
        return subprocess.CompletedProcess(args, 0, "", "")

    def fake_adb(*args, **_kwargs):
        adb_calls.append(args)
        stdout = "1\n" if args[:3] == ("shell", "getprop", "sys.boot_completed") else ""
        return subprocess.CompletedProcess(args, 0, stdout, "")

    monkeypatch.setattr(lifecycle, "_systemctl", fake_systemctl)
    monkeypatch.setattr(lifecycle, "_adb", fake_adb)
    monkeypatch.setattr("helpers.emulator_lifecycle.time.sleep", lambda _value: None)

    report = lifecycle.ensure_ready()
    assert ("start", "dmgongheguo-emulator@poc34.service") in systemctl_calls
    assert ("shell", "input", "keyevent", "82") in adb_calls
    assert report["started_by_run"] is True
    assert report["avd_name"] == "poc34"


def test_emulator_lifecycle_rejects_wrong_running_avd(monkeypatch):
    from helpers.emulator_lifecycle import EmulatorLifecycle, EmulatorLifecycleError

    lifecycle = EmulatorLifecycle(
        adb_path="adb",
        serial="emulator-6554",
        avd_name="poc34",
        logger=logging.getLogger("test"),
        start_timeout=60,
        shutdown_timeout=5,
        manage=True,
        stop_after_run=True,
    )
    monkeypatch.setattr(lifecycle, "_device_state", lambda: "device")
    monkeypatch.setattr(lifecycle, "_actual_avd_name", lambda: "wrong-avd")
    with pytest.raises(EmulatorLifecycleError, match="实际 AVD"):
        lifecycle.ensure_ready()


def test_logged_in_unbound_avd_fails_and_still_stops(monkeypatch, tmp_path):
    main = load_main()

    class FakeLifecycle:
        avd_name = "poc34"
        started_by_run = True

        def __init__(self):
            self.stopped = False

        def ensure_ready(self):
            return {}

        def stop(self):
            self.stopped = True

        def report(self):
            return {"stopped": self.stopped, "avd_name": self.avd_name}

    class FakeWorker:
        def __init__(self, *_args):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    lifecycle = FakeLifecycle()
    monkeypatch.setattr(main, "ensure_ocr_runtime", lambda *_args: (Path("py"), Path("solver"), Path("assets")))
    monkeypatch.setattr(main, "_build_lifecycle", lambda *_args: (lifecycle, 0))
    monkeypatch.setattr(main, "ExclusiveFileLock", lambda *_args: nullcontext())
    monkeypatch.setattr(main, "_sigterm_cleanup_guard", nullcontext)
    monkeypatch.setattr(main, "_check_environment", lambda _adb: {})
    monkeypatch.setattr(main, "_read_account_binding", lambda _adb: None)
    monkeypatch.setattr(main, "OcrWorker", FakeWorker)
    monkeypatch.setattr(main, "_launch_app", lambda _adb: None)
    monkeypatch.setattr(
        main, "_dismiss_announcements", lambda *_args, **_kwargs: 0
    )
    monkeypatch.setattr(
        main,
        "_navigate_my",
        lambda *_args: ("my_logged_in", {"confidence": 0.99}, b"screen"),
    )

    @dataclass
    class Context:
        run_id: int = 1
        instance_id: int = 5
        data_dir: str = str(tmp_path)
        logger: logging.Logger = field(default_factory=lambda: logging.getLogger("test"))

    result = main.run({"account": "first@example.com"}, Context())
    assert result.success is False
    assert "没有账户绑定标记" in result.message
    assert result.data["emulator"]["stopped"] is True


def test_changed_panel_account_is_rebound_once_then_checkin_runs(
    monkeypatch, tmp_path
):
    main = load_main()

    class FakeLifecycle:
        avd_name = "poc34"
        started_by_run = True

        def __init__(self):
            self.stopped = False

        def ensure_ready(self):
            return {}

        def stop(self):
            self.stopped = True

        def report(self):
            return {"stopped": self.stopped, "avd_name": self.avd_name}

    class FakeWorker:
        def __init__(self, *_args):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    lifecycle = FakeLifecycle()
    old_expected = main._expected_binding("first@example.com", "poc34")
    old_binding = {**old_expected, "profile_signature": "a" * 64}
    screens = iter(
        [
            ("my_logged_in", {"confidence": 0.99}, b"old-profile"),
            ("my_logged_out", {"confidence": 0.98}, b"logged-out"),
        ]
    )
    launches: list[bool] = []
    resets: list[bool] = []
    written: list[tuple[dict, str]] = []

    monkeypatch.setattr(
        main,
        "ensure_ocr_runtime",
        lambda *_args: (Path("py"), Path("solver"), Path("assets")),
    )
    monkeypatch.setattr(main, "_build_lifecycle", lambda *_args: (lifecycle, 0))
    monkeypatch.setattr(main, "ExclusiveFileLock", lambda *_args: nullcontext())
    monkeypatch.setattr(main, "_sigterm_cleanup_guard", nullcontext)
    monkeypatch.setattr(main, "_check_environment", lambda _adb: {})
    monkeypatch.setattr(main, "_read_account_binding", lambda _adb: old_binding)
    monkeypatch.setattr(main, "OcrWorker", FakeWorker)
    monkeypatch.setattr(main, "_launch_app", lambda _adb: launches.append(True))
    monkeypatch.setattr(
        main, "_dismiss_announcements", lambda *_args, **_kwargs: 1
    )
    monkeypatch.setattr(main, "_navigate_my", lambda *_args: next(screens))
    monkeypatch.setattr(
        main,
        "_profile_signature",
        lambda _worker, png: "a" * 64 if png == b"old-profile" else "b" * 64,
    )
    monkeypatch.setattr(
        main,
        "_reset_app_for_account_rebind",
        lambda _adb: resets.append(True),
    )
    monkeypatch.setattr(
        main,
        "_login_with_captcha",
        lambda *_args: {"logged_in": True, "captcha_submissions": 1},
    )
    monkeypatch.setattr(
        main,
        "_wait_surface",
        lambda *_args, **_kwargs: (
            "my_logged_in",
            {"confidence": 0.97},
            b"new-profile",
        ),
    )

    def fake_write(_adb, _context, expected, signature):
        written.append((expected, signature))
        return {**expected, "profile_signature": signature}

    monkeypatch.setattr(main, "_write_account_binding", fake_write)
    monkeypatch.setattr(
        main,
        "_perform_daily_checkin",
        lambda *_args: {
            "checked_in": True,
            "already_checked_in": True,
        },
    )

    @dataclass
    class Context:
        run_id: int = 2
        instance_id: int = 5
        data_dir: str = str(tmp_path)
        logger: logging.Logger = field(
            default_factory=lambda: logging.getLogger("test")
        )

    result = main.run(
        {
            "account": "second@example.com",
            "password": "new-password",
            "auto_rebind_account": True,
        },
        Context(),
    )

    assert result.success is True
    assert result.data["account_rebound"] is True
    assert result.data["account_binding_verified"] is True
    assert result.data["already_logged_in"] is False
    assert result.data["announcements_closed"] == 2
    assert result.data["emulator"]["stopped"] is True
    assert len(launches) == 2
    assert resets == [True]
    assert written[0][0]["account_sha256"] == main._account_hash(
        "second@example.com"
    )
    assert written[0][1] == "b" * 64


def test_changed_account_stays_fail_closed_when_auto_rebind_is_disabled(
    monkeypatch, tmp_path
):
    main = load_main()

    class FakeLifecycle:
        avd_name = "poc34"
        started_by_run = True

        def __init__(self):
            self.stopped = False

        def ensure_ready(self):
            return {}

        def stop(self):
            self.stopped = True

        def report(self):
            return {"stopped": self.stopped, "avd_name": self.avd_name}

    lifecycle = FakeLifecycle()
    old_expected = main._expected_binding("first@example.com", "poc34")
    old_binding = {**old_expected, "profile_signature": "a" * 64}
    monkeypatch.setattr(
        main,
        "ensure_ocr_runtime",
        lambda *_args: (Path("py"), Path("solver"), Path("assets")),
    )
    monkeypatch.setattr(main, "_build_lifecycle", lambda *_args: (lifecycle, 0))
    monkeypatch.setattr(main, "ExclusiveFileLock", lambda *_args: nullcontext())
    monkeypatch.setattr(main, "_sigterm_cleanup_guard", nullcontext)
    monkeypatch.setattr(main, "_check_environment", lambda _adb: {})
    monkeypatch.setattr(main, "_read_account_binding", lambda _adb: old_binding)

    @dataclass
    class Context:
        run_id: int = 3
        instance_id: int = 5
        data_dir: str = str(tmp_path)
        logger: logging.Logger = field(
            default_factory=lambda: logging.getLogger("test")
        )

    result = main.run(
        {
            "account": "second@example.com",
            "password": "new-password",
            "auto_rebind_account": False,
        },
        Context(),
    )

    assert result.success is False
    assert "账号绑定不匹配" in result.message
    assert result.data["account_rebind_attempted"] is False
    assert result.data["emulator"]["stopped"] is True
