"""动漫共和国 Android 登录保活与算术验证码离线回归。"""

from __future__ import annotations

import importlib.util
import logging
import sys
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
    assert str(manifest.version) == "1.1.0"
    assert manifest.default_timeout_sec == 1200
    keys = [field.key for field in manifest.fields]
    assert keys[:2] == ["account", "password"]
    assert (ASSETS_DIR / "ui" / "my-logged-out-header.png").is_file()
    assert len(list((ASSETS_DIR / "operators" / "multiply").glob("*.png"))) >= 8
    assert len(list((ASSETS_DIR / "operators" / "other").glob("*.png"))) >= 8


def test_adb_serial_is_fail_closed():
    main = load_main()
    with pytest.raises(main.ScriptError, match="emulator-6554"):
        main.AdbClient("adb", "unexpected-device", logging.getLogger("test"))
