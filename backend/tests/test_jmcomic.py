"""JMComic 签到脚本 v1.6.x 关键契约回归测试。

聚焦"全真浏览器"方案在 6-17/18 真机攻坚中逐个修出来的核心点,且尽量不绑死实现细节:
- v1.6.3: CF 页面判定不得误伤真首页(challenge-platform 脚本会注入所有经 CF 的页面)
- v1.6.4: 区分"会跳转的过渡/挑战页"与"终态封锁页"
- v1.6.6: 点击在元素不可见时回退到 JS click 兜底(登录/签到制胜修复)
- 浮层清理保留目标 modal;manifest 可解析且为 1.6.x
"""
from __future__ import annotations

import importlib.util
import logging
import sys
from types import ModuleType
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
JM_MAIN = ROOT / "scripts" / "jmcomic" / "main.py"
JM_MANIFEST = ROOT / "scripts" / "jmcomic" / "manifest.yaml"


def load_jm_module():
    module_name = "jmcomic_main_under_test"
    spec = importlib.util.spec_from_file_location(module_name, JM_MAIN)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def install_fake_selenium_by(monkeypatch) -> None:
    selenium = ModuleType("selenium")
    webdriver = ModuleType("selenium.webdriver")
    common = ModuleType("selenium.webdriver.common")
    by_mod = ModuleType("selenium.webdriver.common.by")

    class By:
        CSS_SELECTOR = "css selector"

    by_mod.By = By
    monkeypatch.setitem(sys.modules, "selenium", selenium)
    monkeypatch.setitem(sys.modules, "selenium.webdriver", webdriver)
    monkeypatch.setitem(sys.modules, "selenium.webdriver.common", common)
    monkeypatch.setitem(sys.modules, "selenium.webdriver.common.by", by_mod)


# ---- v1.6.3: CF 页面判定不得误伤真首页 ----

def test_is_cf_challenge_page_does_not_misjudge_real_homepage():
    """537KB 真首页即便含 challenge-platform 脚本,title 是业务标题 → 不得判为挑战页。"""
    jm = load_jm_module()
    real = "<html>" + ("x" * 540000) + "challenge-platform/cdn-cgi" + "</html>"
    assert jm._is_cf_challenge_page(real, "最新的English Manga Comics - 禁漫天堂") is False


def test_is_cf_challenge_page_detects_challenge_and_block_pages():
    jm = load_jm_module()
    # 小页面 + 挑战标志
    assert jm._is_cf_challenge_page("<html>cf_chl_opt turnstile</html>", "Just a moment...") is True
    # title 命中(封锁页)
    assert jm._is_cf_challenge_page("<html>x</html>", "Attention Required! | Cloudflare") is True


# ---- v1.6.4: 终态封锁页 vs 可跳转过渡页 ----

def test_is_cf_blocked_page_distinguishes_terminal_block_from_transition():
    jm = load_jm_module()
    assert jm._is_cf_blocked_page("x", "Attention Required! | Cloudflare") is True
    assert jm._is_cf_blocked_page("sorry, you have been blocked by ...", "") is True
    # Just a moment 是会跳转的过渡/JS 挑战,不算终态(给主动 reload 留机会)
    assert jm._is_cf_blocked_page("x", "Just a moment...") is False


# ---- v1.6.6: 点击三层兜底(不可见时走 JS click) ----

def test_genuine_click_falls_back_to_js_click_when_not_visible(monkeypatch):
    jm = load_jm_module()
    install_fake_selenium_by(monkeypatch)
    js_clicks: list = []

    class El:
        def click(self):
            raise RuntimeError("element not interactable")

    class Driver:
        def uc_click(self, sel):
            raise RuntimeError("not visible")

        def find_element(self, by, sel):
            return El()

        def execute_script(self, script, *args):
            if "arguments[0].click()" in script:
                js_clicks.append(args)
            return None

    ok = jm._genuine_click(Driver(), ".login_submit", "登录按钮", logging.getLogger("t"))
    assert ok is True
    assert len(js_clicks) == 1  # uc_click + 普通 click 都失败后,JS click 兜底被调用一次


# ---- 浮层清理 + manifest ----

class FakeOverlayDriver:
    def __init__(self):
        self.calls: list = []

    def execute_script(self, script, *args):
        self.calls.append((script, args))
        return {"hidden": 4, "preserve": args[0]}


def test_dismiss_overlays_hides_ad_layers_but_preserves_target_modal():
    jm = load_jm_module()
    driver = FakeOverlayDriver()
    jm._dismiss_overlays(driver, logging.getLogger("t"), preserve_selector="#login-modal")
    assert driver.calls
    script, args = driver.calls[0]
    assert args == ("#login-modal",)
    assert ".float-right-image" in script and ".black-back" in script


def test_jmcomic_manifest_is_v16x():
    manifest = yaml.safe_load(JM_MANIFEST.read_text(encoding="utf-8"))
    assert str(manifest["version"]).startswith("1.6")
