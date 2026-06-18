r"""JMComic(18comic.vip)每日签到 — v1.6.6 全程真浏览器(账密登录 + 真实点击签到)。

================================================================
为什么是 v1.6.x(2026-06-17/18 多轮真机验证后的最终方向)
================================================================
6-17 起 Cloudflare 把这站的防护等级调高:**只有"真实浏览器上下文"里的请求才认 cf_clearance**。
逐一排除(全部真机验证):
- 纯 requests(v1.1)、浏览器内 fetch(v1.2/1.3)、curl_cffi 模拟 Chrome(v1.4/1.5)—— 全部 403。
- 换出口 IP(韩国代理)curl_cffi 仍 403 → 区分变量不是 IP,是"真实浏览器 vs 程序请求"。
- 用户手动用真浏览器(走本 VPS 出口 IP)人工登录签到 → 成功。

结论:别再把 cf_clearance 拿出来给独立客户端/脚本 fetch 重放了。**让登录和签到都在真浏览器里、以真实点击触发页面自己的 $.post 完成**,这才和"真人能成功"对齐。

实现要点:
- SeleniumBase UC(uc=True)+ Xvfb 虚拟屏(无头服务器靠它;过 CF 的 uc_gui_click_captcha 一直在 Xvfb 上跑,有效)。
- 登录:导航首页过 CF → 显示 #login-modal → 填 #login_username_/#login_password → **uc_click('.login_submit')**
  真实点击 → 触发页面原生 `$.post('/login')`(genuine 上下文,CF 放行)。
- 签到:导航 /user/(已登录) → 显示 #bouns-popup → **uc_click('.login-bouns')** 真实点击 →
  触发页面原生 `$.post('/ajax/user_daily_sign')`。
- 结果判定:读页面 DOM(不发任何额外请求)。.login-bouns 被禁用 / 文字含"已簽到" = 已签;
  /user/ 含 data-dailyid = 已登录。
- **关键**:全程不用 requests / 不用 execute_async_script fetch / 不用 curl —— 这些都会被 CF 当程序请求拦。
  点击用 uc_click(CDP 断开重连,模拟真人);读取用 driver.page_source(读已加载的 DOM,非请求)。

DOM 选择器(抓包还原 jm2.har / jm.har):
- 登录模态框 #login-modal;用户名 #login_username_;密码 #login_password;记住180天 #login_remember;
  提交按钮 .login_submit(点它 → 页面 serialize 表单 + '&submit_login=1' → $.post('/login'))
- 签到弹窗 #bouns-popup;签到按钮 .login-bouns("立即簽到");已签 → 按钮禁用 + 文字"已簽到"
- /login 会 301 跳首页(https://18comic.vip),登录表单在首页 DOM

历史:v1.0/1.1 selenium+requests | v1.2/1.3 浏览器内 fetch | v1.4/1.5 curl_cffi(+代理)| v1.6 全真浏览器
v1.6.1:首页大 HTML/广告浮层适配。等登录按钮真正出现,失败重导航一次;点击前隐藏广告/浮层但保留目标 modal;失败输出 DOM 诊断。
v1.6.2:① CF 拦截页检测扩到 "Attention Required"/被封锁/1020(原来只认 "Just a moment",会把被封页误当过盾);
       ② 出口回退——配了 proxy 先走 proxy,被 CF 拦/页面加载不出/网络错则自动回退本机 VPS IP 直连(真人验证过能成功的环境),不消耗 max_retries;
       ③ 重导航补一次 Turnstile 点击 + 过 CF 阶段输出 title/page_len 诊断。
v1.6.3:修 v1.6.2 误判——CF 的 challenge-platform 脚本会注入所有经其代理的页面(含 537KB 真首页),旧判定把真首页也当挑战页 → 本机过了 CF 却被判失败。
       改用 title 强特征 + 页面体积守卫(真首页 >100KB 不再误判),全部判定点传入 title;过 CF 点击间隔 6→9 秒(给 Turnstile 更充裕评估时间)。
v1.6.4:修过渡态竞态——点击 Turnstile 拿到 cf_clearance 后,页面可能还停在 "Just a moment" 过渡页(JS 正跳转真首页),旧逻辑立即判定会误抓这一瞬判失败。
       拿到 clearance 后轮询等页面跳转到真首页(最多 ~24s);Attention Required/封锁是终态不会跳转,立即判失败回退本机(新增 _is_cf_blocked_page 区分)。
v1.6.5:真机发现点击 captcha 后页面持续卡 "Just a moment" 不跳转(CDP 重连打断 CF 自动跳转),被动等无效。
       借鉴 6-16 的 v1.1.0(拿到 cf_clearance 就够):拿到 clearance 后主动带 cookie 重新导航首页(uc_open_with_reconnect)最多 3 次,让 CF 放行真首页;封锁页(终态)不 reload 直接回退。
v1.6.6:真机 run 121 本机已跑通过 CF→546KB 真首页→找到登录框→填表 OK,只差点击登录按钮失败(.login_submit 在 modal 里不可见,uc_click/普通 click 都要求可见)。
       _genuine_click 加第三层 JS click 兜底(execute_script arguments[0].click()):绕过可见性直接触发 click handler → 页面原生 $.post(登录/签到非过 CF,请求仍由真浏览器发出,无需真人鼠标)。
"""
from __future__ import annotations

import importlib.util
import os
import random
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ============================================================
# 平台协议:RunResult
# ============================================================
@dataclass
class RunResult:
    success: bool
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)


# ============================================================
# URL + 选择器常量
# ============================================================
BASE_URL = "https://18comic.vip"
HOME_URL = "https://18comic.vip/"
USER_URL = "https://18comic.vip/user/"

SEL_LOGIN_MODAL = "#login-modal"
SEL_USERNAME = "#login_username_"
SEL_PASSWORD = "#login_password"
SEL_REMEMBER = "#login_remember"
SEL_LOGIN_SUBMIT = ".login_submit"
SEL_SIGN_POPUP = "#bouns-popup"
SEL_SIGN_BTN = ".login-bouns"


# ============================================================
# 业务异常
# ============================================================
class JmError(Exception):
    def __init__(self, message: str, **diag: Any) -> None:
        super().__init__(message)
        self.diag = diag

    def to_data(self) -> dict[str, Any]:
        return {"error_class": self.__class__.__name__, **self.diag}


class JmAlreadySignedToday(JmError):
    """已签到。平台语义 = success。"""


class JmCloudflareBlocked(JmError):
    """被 CF 拦(导航出现 Just a moment 挑战页 / 拿不到 cf_clearance)。"""


class JmLoginFailed(JmError):
    """账号/密码错误(登录后仍非登录态且判定为凭证问题)。无重试价值。"""


class JmLoginEndpointError(JmError):
    """登录流程异常(模态框未出现 / 点击失败 / 登录后仍未登录态)。可重试。"""


class JmSignEndpointError(JmError):
    """签到流程异常(弹窗/按钮未出现 / 点击后未检测到已签)。可重试。"""


class JmNetworkError(JmError):
    """浏览器导航/交互的底层异常。"""


# ============================================================
# 依赖自动安装(seleniumbase + xvfbwrapper + 系统库 + Chrome)
# ============================================================
def _ensure_dependencies(logger) -> None:
    required_packages = {"seleniumbase": "seleniumbase", "xvfbwrapper": "xvfbwrapper"}
    missing = [pkg for mod, pkg in required_packages.items() if importlib.util.find_spec(mod) is None]
    if missing:
        logger.info(f"检测到缺失 Python 依赖: {missing},正在自动安装...")
        subprocess.check_call([
            sys.executable, "-m", "pip", "install",
            "--break-system-packages", "--ignore-installed", "--quiet", *missing
        ])
        logger.info("Python 依赖安装完成")

    if sys.platform.startswith("linux"):
        subprocess.run(
            ["apt-get", "install", "-y", "-q",
             "libnspr4", "libnss3", "libgbm1", "libasound2",
             "libx11-xcb1", "libxcb-dri3-0", "libdrm2",
             "libxcomposite1", "libxdamage1", "libxrandr2",
             "libpango-1.0-0", "libcairo2", "libatspi2.0-0",
             "fonts-liberation", "libvulkan1"],
            capture_output=True,
        )
        system_pkgs: list[str] = []
        if subprocess.run(["which", "Xvfb"], capture_output=True).returncode != 0:
            system_pkgs.append("xvfb")
        if subprocess.run(["python3", "-c", "import tkinter"], capture_output=True).returncode != 0:
            system_pkgs += ["python3-tk", "python3-dev"]
        if system_pkgs:
            logger.info(f"检测到缺失系统依赖: {system_pkgs},正在安装...")
            subprocess.check_call(["apt-get", "install", "-y"] + system_pkgs)
            logger.info("系统依赖安装完成")
        has_chrome = (
            subprocess.run(["which", "google-chrome"], capture_output=True).returncode == 0
            or subprocess.run(["which", "google-chrome-stable"], capture_output=True).returncode == 0
        )
        if not has_chrome:
            logger.info("未检测到 Google Chrome,正在下载安装 Chrome Stable...")
            subprocess.check_call([
                "bash", "-c",
                "wget -q -O /tmp/chrome.deb "
                "https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb "
                "&& apt-get install -y /tmp/chrome.deb"
            ])
            logger.info("Google Chrome 安装完成")

    try:
        import seleniumbase
        sb_drivers_dir = Path(seleniumbase.__file__).parent / "drivers"
        has_driver = (sb_drivers_dir / "chromedriver").exists() or (sb_drivers_dir / "uc_driver").exists()
    except Exception:
        has_driver = False
    if not has_driver:
        logger.info("ChromeDriver 未找到,通过 seleniumbase 自动下载...")
        subprocess.check_call(["seleniumbase", "install", "chromedriver"])
        logger.info("ChromeDriver 安装完成")


# ============================================================
# 浏览器:Xvfb + UC,过 CF,保持存活
# ============================================================
def _open_browser_pass_cf(logger, context, proxy: str | None = None):
    """打开 Xvfb + Chrome UC,导航首页过 CF Turnstile,返回 (driver, vdisplay)。失败 raise。"""
    from xvfbwrapper import Xvfb
    from seleniumbase import Driver

    logger.info("启动 Xvfb 虚拟显示器(无头服务器靠它给 UC 一个真实屏幕)...")
    vdisplay = Xvfb(width=1280, height=800)
    vdisplay.start()
    os.environ["DISPLAY"] = f":{vdisplay.new_display}"

    driver_kwargs: dict[str, Any] = {"uc": True, "headless": False}
    if proxy:
        driver_kwargs["proxy"] = proxy
        logger.info(f"启动 Chrome UC(走代理 {proxy})...")
    else:
        logger.info("启动 Chrome UC...")
    driver = Driver(**driver_kwargs)
    try:
        logger.info(f"导航首页过 CF: {HOME_URL}")
        driver.uc_open_with_reconnect(HOME_URL, reconnect_time=4)

        def get_cf() -> str | None:
            for c in driver.get_cookies():
                if c["name"] == "cf_clearance":
                    return c["value"]
            return None

        logger.info("等待 CF 后台完成初始评估(15 秒)...")
        time.sleep(15)
        passed = bool(get_cf())
        for attempt in range(5):
            if passed:
                break
            logger.info(f"第 {attempt + 1} 次尝试点击 CF Turnstile...")
            try:
                driver.uc_gui_click_captcha()
            except Exception:
                pass
            time.sleep(9)
            if get_cf():
                passed = True
                break
            logger.info(f"第 {attempt + 1} 次未获取到 cf_clearance,继续重试...")

        # 拿到 cf_clearance 后,页面常卡在 "Just a moment"(点击 captcha 的 CDP 重连打断了 CF 自动跳转,
        # 被动等不来)。借鉴 v1.1.0:拿到 clearance 就主动带着它重新导航首页(真浏览器+有效 cookie → CF 放行真首页)。
        # Attention Required/封锁是终态(IP 被挡),reload 也没用 → 立即判失败回退本机,不浪费时间。
        html = driver.page_source or ""
        try:
            ctitle = driver.title
        except Exception:
            ctitle = "?"
        reload_n = 0
        while (passed and _is_cf_challenge_page(html, ctitle)
               and not _is_cf_blocked_page(html, ctitle) and reload_n < 3):
            reload_n += 1
            logger.info(f"已拿 cf_clearance 但页面仍={ctitle!r} len={len(html)},主动重新导航首页(第{reload_n}次,带 clearance 进真首页)...")
            try:
                driver.uc_open_with_reconnect(HOME_URL, reconnect_time=4)
                time.sleep(5)
            except Exception as exc:
                logger.warning(f"重新导航异常(继续): {exc}")
            try:
                html = driver.page_source or ""
                ctitle = driver.title
            except Exception:
                break
        if _is_cf_challenge_page(html, ctitle):
            raise JmCloudflareBlocked(
                f"停在 CF 拦截/挑战页(title={ctitle!r} page_len={len(html)} cf_clearance={'有' if passed else '无'} reloads={reload_n})",
                stage="open_pass_cf",
            )
        logger.info(
            f"✓ CF 通过(cf_clearance={'有' if passed else '无但非拦截页'} title={ctitle!r} page_len={len(html)} reloads={reload_n}),浏览器保持存活"
        )
        try:
            logger.info(f"UA: {driver.execute_script('return navigator.userAgent')[:60]}...")
        except Exception:
            pass
        return driver, vdisplay
    except Exception as exc:
        _try_save_error_screenshot(driver, context, logger)
        _quit_browser(driver, vdisplay)
        if isinstance(exc, JmCloudflareBlocked):
            raise
        logger.error(f"浏览器过 CF 异常: {exc}")
        raise JmCloudflareBlocked(f"浏览器过 CF 异常: {exc}") from exc


def _quit_browser(driver, vdisplay) -> None:
    try:
        if driver is not None:
            driver.quit()
    except Exception:
        pass
    try:
        if vdisplay is not None:
            vdisplay.stop()
    except Exception:
        pass


def _try_save_error_screenshot(driver, context, logger) -> None:
    try:
        data_dir = getattr(context, "data_dir", "") or ""
        if data_dir and driver is not None:
            ts = int(time.time())
            path = Path(data_dir) / f"cf_error_{ts}.png"
            driver.save_screenshot(str(path))
            logger.info(f"失败截图已存: {path}")
    except Exception as exc:
        logger.warning(f"保存失败截图未能完成: {exc}")


def _is_cf_challenge_page(html: str, title: str = "") -> bool:
    """判断是否停在 CF 挑战/拦截页(而非真实业务页)。

    ⚠️ 关键:CF 的 ``challenge-platform`` 脚本会注入到**所有**经其代理的页面(含正常真首页),
    绝不能拿它当判据,否则 537KB 真首页也会被误判为挑战页(v1.6.2 踩过这个坑)。
    改用 title 强特征 + 页面体积守卫:真首页通常 >100KB 且 title 是业务标题;
    挑战/拦截页通常 <30KB 且 title 是 CF 文案(Just a moment / Attention Required)。
    """
    low = (html or "").lower()
    t = (title or "").lower()
    n = len(low)
    # 1) title 命中 CF 文案(真实业务页 title 绝不会是这些)
    if any(k in t for k in ("just a moment", "attention required", "access denied", "请稍候", "请稍后")):
        return True
    # 2) 明确封锁文案(强特异,真首页不含)
    if any(k in low for k in (
        "sorry, you have been blocked", "you have been blocked by",
        "error 1020", "cf-error-details",
    )):
        return True
    # 3) 小页面 + 挑战标志(真首页 >100KB;挑战/拦截页通常 <30KB,体积守卫防误伤真首页)
    if n < 30000 and any(k in low for k in (
        "just a moment", "cf-browser-verification", "turnstile",
        "cf_chl_opt", "challenge-platform", "/cdn-cgi/challenge",
    )):
        return True
    return False


def _is_cf_blocked_page(html: str, title: str = "") -> bool:
    """终态封锁页(出口 IP 被挡,等也不会自己跳转):Attention Required / blocked / 1020。
    与 _is_cf_challenge_page 的区别:'Just a moment' 是会跳转的过渡/JS 挑战,不算终态。"""
    low = (html or "").lower()
    t = (title or "").lower()
    return (
        "attention required" in t or "access denied" in t
        or "sorry, you have been blocked" in low
        or "you have been blocked by" in low
        or "error 1020" in low or "cf-error-details" in low
    )


# ============================================================
# 真实点击 helper(尽量 CDP 断开模拟真人;退化为普通点击)
# ============================================================
def _genuine_click(driver, selector: str, label: str, logger) -> bool:
    """优先 uc_click(模拟真人)→ 普通 click → JS click 兜底。返回是否点击成功。

    登录/签到按钮常在 modal 里、可能不可见(modal 未正常弹出),uc_click/普通 click 都要求可见;
    JS click 绕过可见性直接触发元素 click handler → 页面原生 $.post。这是登录/签到步骤(非过 CF),
    请求仍由真浏览器上下文发出(带 cf_clearance+cookie),不需要真人鼠标轨迹。
    """
    from selenium.webdriver.common.by import By
    # 1) SeleniumBase UC 的 uc_click(最接近真人)
    uc_click = getattr(driver, "uc_click", None)
    if callable(uc_click):
        try:
            uc_click(selector)
            logger.info(f"✓ uc_click [{label}] ({selector})")
            return True
        except Exception as exc:
            logger.warning(f"uc_click [{label}] 失败({type(exc).__name__}),尝试普通点击")
    # 2) 普通 WebDriver 点击(需元素可见可交互)
    try:
        el = driver.find_element(By.CSS_SELECTOR, selector)
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        except Exception:
            pass
        el.click()
        logger.info(f"✓ 普通 click [{label}] ({selector})")
        return True
    except Exception as exc:
        logger.warning(f"普通 click [{label}] 失败({type(exc).__name__}),尝试 JS click 兜底")
    # 3) JS click 兜底:绕过可见性,直接触发元素 click handler → 页面原生 $.post
    try:
        el = driver.find_element(By.CSS_SELECTOR, selector)
        driver.execute_script("arguments[0].click();", el)
        logger.info(f"✓ JS click [{label}] ({selector})(绕过可见性触发 handler)")
        return True
    except Exception as exc:
        logger.error(f"点击 [{label}] ({selector}) 三种方式均失败: {type(exc).__name__}: {exc}")
        return False


def _js_show_modal(driver, selector: str, logger) -> None:
    """用页面自带 jQuery+Bootstrap 显示模态框(仅展示 UI,非敏感请求)。"""
    try:
        driver.execute_script(
            "if(window.jQuery){jQuery(arguments[0]).modal('show');}", selector
        )
    except Exception as exc:
        logger.warning(f"显示模态框 {selector} 异常(继续): {exc}")


_JS_DISMISS_OVERLAYS = (
    "var preserve=arguments[0];"
    "var hidden=0;"
    "function keep(el){try{return preserve&&(el.matches(preserve)||el.closest(preserve));}catch(e){return false;}}"
    "function hide(el){if(!el||keep(el))return;el.style.setProperty('display','none','important');"
    "el.style.setProperty('visibility','hidden','important');el.style.setProperty('pointer-events','none','important');"
    "el.classList.remove('show','in');hidden++;}"
    "['.float-right-image','.black-back','.modal-backdrop','.change-energy-popup','.modal.show','.modal.in',"
    "'.modal[style*=\"display: block\"]'].forEach(function(sel){"
    "document.querySelectorAll(sel).forEach(hide);});"
    "try{localStorage.setItem('float-right-image-close','1');}catch(e){}"
    "if(document.body){document.body.style.overflow='';document.body.style.paddingRight='';}"
    "return {hidden:hidden,preserve:preserve};"
)


def _dismiss_overlays(driver, logger, preserve_selector: str | None = None) -> None:
    """隐藏可能遮挡真实点击的广告/浮层; preserve_selector 指定的目标 modal 不动。"""
    try:
        result = driver.execute_script(_JS_DISMISS_OVERLAYS, preserve_selector)
        hidden = result.get("hidden") if isinstance(result, dict) else result
        if hidden:
            logger.info(f"已清理可能遮挡点击的广告/浮层 hidden={hidden} preserve={preserve_selector}")
    except Exception as exc:
        logger.warning(f"清理广告/浮层异常(继续): {type(exc).__name__}: {exc}")


# ============================================================
# 登录(真浏览器:填表单 + 真实点击触发页面原生 $.post('/login'))
# ============================================================
def _wait_present(driver, selector: str, timeout: int, logger) -> bool:
    """轮询等待某 CSS 选择器出现在 DOM(find_elements 不抛异常)。"""
    from selenium.webdriver.common.by import By
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            if driver.find_elements(By.CSS_SELECTOR, selector):
                return True
        except Exception:
            pass
        time.sleep(1.0)
    return False


# 诊断:列出页面关键登录元素 + jQuery/标题等(找不到登录框时输出,便于真机定位)
_JS_LOGIN_DIAG = (
    "var a=[];"
    "document.querySelectorAll(\"input[name='username'],input[name='password'],.login_submit\")"
    ".forEach(function(e){a.push(e.outerHTML.slice(0,140));});"
    "return {jq:(typeof window.jQuery!=='undefined'), cnt:a.length, els:a.slice(0,6)};"
)


def _log_login_diag(driver, logger) -> None:
    try:
        html = driver.page_source or ""
    except Exception:
        html = ""
    try:
        title = driver.title
    except Exception:
        title = "?"
    try:
        url = driver.current_url
    except Exception:
        url = "?"
    logger.warning(
        f"[诊断] url={url} title={title!r} page_len={len(html)} "
        f"is_challenge={_is_cf_challenge_page(html, title)} "
        f"has_login_modal={'login-modal' in html} has_login_username_={'login_username_' in html} "
        f"has_login_submit={'login_submit' in html}"
    )
    try:
        info = driver.execute_script(_JS_LOGIN_DIAG)
        logger.warning(f"[诊断] jQuery={info.get('jq')} 关键元素数={info.get('cnt')} els={info.get('els')}")
    except Exception as exc:
        logger.warning(f"[诊断] 执行元素探测异常: {exc}")


# JS:定位 .login_submit 所在 form,设其 username/password/remember(不依赖元素可见,最稳)
_JS_FILL_LOGIN = (
    "var btn=document.querySelector(arguments[0]);"
    "if(!btn){return 'NO_SUBMIT_BTN';}"
    "var form=btn.closest('form');"
    "if(!form){return 'NO_FORM';}"
    "var u=form.querySelector(\"[name='username']\");"
    "var p=form.querySelector(\"[name='password']\");"
    "var r=form.querySelector(\"[name='login_remember']\");"
    "if(!u||!p){return 'NO_FIELDS';}"
    "u.value=arguments[1];p.value=arguments[2];if(r){r.checked=true;}"
    "return 'OK';"
)


def _genuine_login(driver, username: str, password: str, logger) -> None:
    """真浏览器账密登录:等登录按钮出现 → JS 填表(定位按钮所在 form)→ 真实点击触发页面原生 $.post('/login')。"""
    # 1) 等登录提交按钮出现(过 CF 后真首页可能还没加载完;走慢代理时大页面更易加载不全)
    if not _wait_present(driver, SEL_LOGIN_SUBMIT, 12, logger):
        logger.info("首页暂未见登录按钮,重新导航首页(并重新过一次 CF)后再等...")
        try:
            driver.uc_open_with_reconnect(HOME_URL, reconnect_time=4)
            time.sleep(3.0)
            try:  # 重导航可能再次触发 CF,补一次 Turnstile 点击(无挑战时无副作用)
                driver.uc_gui_click_captcha()
            except Exception:
                pass
        except Exception as exc:
            logger.warning(f"重新导航首页异常(继续): {exc}")
        time.sleep(2.0)
        if not _wait_present(driver, SEL_LOGIN_SUBMIT, 18, logger):
            _log_login_diag(driver, logger)
            # 区分:停在 CF 拦截页(换出口有救,抛 CF blocked 触发回退)vs 真首页没加载出按钮
            try:
                _html = driver.page_source or ""
            except Exception:
                _html = ""
            try:
                _title = driver.title
            except Exception:
                _title = ""
            if _is_cf_challenge_page(_html, _title):
                raise JmCloudflareBlocked(
                    "首页被 Cloudflare 拦截(Attention Required/挑战页)— 此出口 IP 过不了盾",
                    stage="wait_login_form_cf",
                )
            raise JmLoginEndpointError(
                "登录按钮 .login_submit 始终未出现(真首页未加载完 / 选择器变化)", stage="wait_login_form",
            )
    logger.info("登录入口已就绪")

    # 2) 显示登录模态框(让提交按钮可点)+ JS 填表
    _dismiss_overlays(driver, logger)
    _js_show_modal(driver, SEL_LOGIN_MODAL, logger)
    time.sleep(1.5)
    _dismiss_overlays(driver, logger, preserve_selector=SEL_LOGIN_MODAL)
    try:
        ret = driver.execute_script(_JS_FILL_LOGIN, SEL_LOGIN_SUBMIT, username, password)
    except Exception as exc:
        _log_login_diag(driver, logger)
        raise JmLoginEndpointError(f"JS 填写登录表单异常: {type(exc).__name__}: {exc}", stage="fill_login_form") from exc
    logger.info(f"填表结果: {ret}")
    if ret != "OK":
        _log_login_diag(driver, logger)
        raise JmLoginEndpointError(f"填写登录表单失败(返回 {ret})", stage="fill_login_form", fill_ret=ret)

    # 3) 真实点击登录按钮 → 触发页面原生 $.post('/login')
    time.sleep(0.6)
    logger.info("真实点击登录按钮 .login_submit(触发页面原生 $.post('/login'))...")
    if not _genuine_click(driver, SEL_LOGIN_SUBMIT, "登录按钮", logger):
        raise JmLoginEndpointError("点击登录按钮失败", stage="click_login")
    logger.info("已点击登录,等待登录完成(页面成功后会跳转)...")
    time.sleep(5.0)


def _goto_user_and_get_daily_id(driver, logger) -> str:
    """导航 /user/(genuine),确认登录态并取 daily_id。

    raise JmCloudflareBlocked / JmLoginFailed(未登录态)。
    """
    logger.info(f"导航 {USER_URL}(验证登录态 + 取 daily_id)...")
    try:
        driver.uc_open_with_reconnect(USER_URL, reconnect_time=3)
    except Exception as exc:
        raise JmNetworkError(f"导航 /user/ 失败: {type(exc).__name__}: {exc}") from exc
    time.sleep(2.0)
    html = driver.page_source or ""
    try:
        _t = driver.title
    except Exception:
        _t = ""
    if _is_cf_challenge_page(html, _t):
        raise JmCloudflareBlocked("导航 /user/ 被 CF 拦(出现挑战页)", stage="goto_user")
    m = re.search(r'data-dailyid=["\'](\d+)["\']', html)
    if m:
        logger.info(f"✓ 已登录(/user/ 含 data-dailyid={m.group(1)})")
        return m.group(1)
    # 未登录:可能账密错,或登录没生效
    logged_markers = ("logout" in html.lower()) or ("userdetails" in html.lower())
    snippet = re.sub(r"\s+", " ", html[:300])
    raise JmLoginFailed(
        "登录后 /user/ 仍非登录态(账密可能错误,或登录未生效)",
        stage="verify_login", logged_markers=logged_markers, page_head=snippet,
    )


# ============================================================
# 签到(真浏览器:真实点击 .login-bouns 触发页面原生 $.post)
# ============================================================
def _read_sign_button_state(driver, logger) -> tuple[bool, str]:
    """读 .login-bouns 按钮状态。返回 (是否已签, 按钮文字)。读 DOM 不发请求。"""
    from selenium.webdriver.common.by import By
    try:
        btn = driver.find_element(By.CSS_SELECTOR, SEL_SIGN_BTN)
        text = (btn.text or "").strip()
        enabled = btn.is_enabled()
        already = (not enabled) or any(k in text for k in ("已簽", "已签", "已經簽", "已经签"))
        logger.info(f".login-bouns 文字={text!r} enabled={enabled} → 已签={already}")
        return already, text
    except Exception as exc:
        logger.warning(f"读取签到按钮状态异常: {type(exc).__name__}: {exc}")
        return False, ""


def _genuine_sign(driver, daily_id: str, logger) -> dict[str, Any]:
    """显示签到弹窗 → 若未签则真实点击签到 → 重载 /user/ 读结果。

    return: {"category": "signed_now"|"already_signed_today", "detail": ...}
    raise JmSignEndpointError / JmCloudflareBlocked。
    """
    logger.info("显示签到弹窗 #bouns-popup ...")
    _dismiss_overlays(driver, logger)
    _js_show_modal(driver, SEL_SIGN_POPUP, logger)
    time.sleep(2.0)
    _dismiss_overlays(driver, logger, preserve_selector=SEL_SIGN_POPUP)

    already, text = _read_sign_button_state(driver, logger)
    if already:
        return {"category": "already_signed_today", "detail": text or "按钮已禁用/已签到"}

    logger.info("真实点击签到按钮 .login-bouns(触发页面原生 $.post('/ajax/user_daily_sign'))...")
    if not _genuine_click(driver, SEL_SIGN_BTN, "签到按钮", logger):
        raise JmSignEndpointError("点击签到按钮失败", stage="click_sign")
    time.sleep(4.0)

    # 重载 /user/,让页面 singFun 重跑;已签则按钮会被禁用/文字变「已簽到」
    logger.info("重载 /user/ 确认签到结果...")
    try:
        driver.uc_open_with_reconnect(USER_URL, reconnect_time=3)
        time.sleep(2.0)
    except Exception as exc:
        logger.warning(f"重载 /user/ 异常(用当前页判定): {exc}")
    html = driver.page_source or ""
    try:
        _t2 = driver.title
    except Exception:
        _t2 = ""
    if _is_cf_challenge_page(html, _t2):
        raise JmCloudflareBlocked("重载 /user/ 被 CF 拦", stage="recheck_sign")
    _js_show_modal(driver, SEL_SIGN_POPUP, logger)
    time.sleep(1.5)
    already2, text2 = _read_sign_button_state(driver, logger)
    if already2:
        logger.info("✓ 签到成功(签到后按钮已变已签状态)")
        return {"category": "signed_now", "detail": text2 or "签到后按钮已禁用"}

    # 兜底:页面文本扫已签 marker
    for marker in ("今日已簽到", "已簽到", "今日已签到", "已签到", "已經簽到"):
        if marker in html:
            logger.info(f"✓ 兜底:页面含 '{marker}' = 已签")
            return {"category": "signed_now", "detail": marker}

    raise JmSignEndpointError(
        "点击签到后未检测到已签状态(可能点击未触发或被拦)",
        stage="post_sign_check", btn_text=text2,
    )


# ============================================================
# 平台基础:分块 sleep
# ============================================================
def _chunked_sleep(total_sec: int, chunk: int = 30) -> None:
    remaining = total_sec
    while remaining > 0:
        time.sleep(min(chunk, remaining))
        remaining -= chunk


# ============================================================
# 一次完整尝试:开浏览器过 CF → 账密登录 → 签到 → 关浏览器
# 出口策略:配了 proxy 先走 proxy,被 CF 拦/页面加载不出/网络错 → 自动回退本机 VPS IP 直连
# ============================================================
def _attempt_via_outlet(config: dict, context: Any, logger, proxy: str | None) -> RunResult:
    """用指定出口(proxy 或 None=本机直连)完整跑一次:过 CF → 登录 → 签到。"""
    username = (config.get("username") or "").strip()
    password = (config.get("password") or "").strip()
    outlet_tag = proxy or "vps-direct"
    driver = None
    vdisplay = None
    try:
        driver, vdisplay = _open_browser_pass_cf(logger, context, proxy)
        _genuine_login(driver, username, password, logger)
        daily_id = _goto_user_and_get_daily_id(driver, logger)
        result = _genuine_sign(driver, daily_id, logger)
        cat = result.get("category", "signed_now")
        if cat == "already_signed_today":
            return RunResult(success=True, message=f"今日已签到过了: {result.get('detail','')}",
                             data={"category": cat, "outlet": outlet_tag, **result})
        return RunResult(success=True, message=f"签到成功: {result.get('detail','')}",
                         data={"category": cat, "outlet": outlet_tag, **result})
    finally:
        _quit_browser(driver, vdisplay)


def _attempt_once(config: dict, context: Any, logger) -> RunResult:
    """单次尝试。配了 proxy 则先走 proxy,失败(CF 拦/页面加载/网络)自动回退本机 VPS IP 直连。

    回退发生在单次 attempt 内部,不消耗 max_retries。账密错(JmLoginFailed)/签到按钮问题
    (JmSignEndpointError)与出口 IP 无关,直接上抛不回退。
    """
    proxy = (config.get("proxy") or "").strip() or None
    outlets = [proxy, None] if proxy else [None]  # 配了代理:先代理、本机保底;没配:直接本机
    last_exc: Exception | None = None
    for idx, outlet in enumerate(outlets):
        tag = f"代理出口 {outlet}" if outlet else "本机 VPS IP 直连"
        if idx > 0:
            logger.warning(f"⚠️ 上一出口失败,回退到【{tag}】重试本次尝试(不消耗 max_retries)...")
        else:
            logger.info(f"本次尝试出口:【{tag}】")
        try:
            return _attempt_via_outlet(config, context, logger, outlet)
        except JmLoginFailed:
            raise  # 账密错,换出口也救不了
        except (JmCloudflareBlocked, JmLoginEndpointError, JmNetworkError) as exc:
            last_exc = exc
            logger.error(f"出口【{tag}】失败({type(exc).__name__}): {exc}")
            # 仍有下一出口则继续回退;否则循环结束后抛 last_exc
    raise last_exc if last_exc else JmNetworkError("所有出口均失败且无明确异常")


# ============================================================
# 平台主入口
# ============================================================
def run(config: dict, context: Any) -> RunResult:
    logger = context.logger
    if context.run_id == 0 and context.instance_id == 0:
        return RunResult(success=True, message="dry-run OK")

    username = (config.get("username") or "").strip()
    password = (config.get("password") or "").strip()
    delay = int(config.get("random_delay_sec", 0) or 0)
    max_retries = int(config.get("max_retries", 3) or 3)
    retry_interval = int(config.get("retry_interval_sec", 300) or 300)

    if not username or not password:
        logger.error("username 或 password 字段为空")
        return RunResult(success=False, message="请填写 JM 用户名 + 密码(v1.6.1 改用账密真浏览器登录)")

    trigger_type = str(getattr(context, "trigger_type", "scheduled") or "scheduled")
    if trigger_type == "manual" and delay > 0:
        logger.info(f"trigger_type=manual(用户立即触发)→ 跳过 random_delay({delay}s)立即开始")
        delay = 0
    instance_timeout = int(getattr(context, "timeout_sec", 0) or 0)
    estimated_budget = 180 + (max_retries - 1) * retry_interval
    safe_budget = max(0, instance_timeout - estimated_budget)
    if instance_timeout > 0 and delay > safe_budget:
        original = delay
        delay = safe_budget
        logger.warning(
            f"random_delay_sec={original} > 实例 timeout({instance_timeout}) - 预估业务耗时({estimated_budget}),"
            f"会被超时强杀。临时 cap 到 {delay}s。建议 timeout_sec ≥ {original + estimated_budget}。"
        )
    if delay > 0:
        sleep_sec = random.randint(0, delay)
        if sleep_sec > 0:
            logger.info(f"随机延迟 {sleep_sec} 秒后开始签到(配置上限 {delay}s)...")
            _chunked_sleep(sleep_sec)
        else:
            logger.info("随机延迟掷骰得 0,立即开始")
    else:
        logger.info("随机延迟禁用,立即开始")

    try:
        _ensure_dependencies(logger)
    except subprocess.CalledProcessError as exc:
        logger.error(f"依赖安装失败: {exc}")
        return RunResult(success=False, message=f"依赖安装失败(可能权限不足或网络问题): {exc}")

    last_exc: Exception | None = None
    for attempt in range(1, max_retries + 1):
        logger.info(f"========= 第 {attempt}/{max_retries} 次尝试(真浏览器:过 CF → 账密登录 → 签到)=========")
        try:
            return _attempt_once(config, context, logger)
        except JmLoginFailed as exc:
            logger.error(f"登录失败(疑似账密错),无重试: {exc}")
            return RunResult(success=False, message=str(exc), data={"category": "login_failed", **exc.to_data()})
        except (JmCloudflareBlocked, JmLoginEndpointError, JmSignEndpointError, JmNetworkError) as exc:
            last_exc = exc
            logger.error(f"第 {attempt} 次失败({type(exc).__name__}): {exc}")
        except Exception as exc:
            last_exc = exc
            logger.exception(f"第 {attempt} 次未知异常 ({type(exc).__name__})")
        if attempt < max_retries:
            logger.info(f"将在 {retry_interval} 秒后整体重试...")
            _chunked_sleep(retry_interval)

    last_diag: dict[str, Any] = {}
    if isinstance(last_exc, JmError):
        last_diag = last_exc.to_data()
    elif last_exc is not None:
        last_diag = {"error_class": type(last_exc).__name__}
    return RunResult(
        success=False,
        message=f"已达到最大重试次数 {max_retries},最后错误: {last_exc}",
        data={
            "category": "exhausted_retries", "max_retries": max_retries,
            "retry_interval_sec": retry_interval,
            "last_error_repr": repr(last_exc) if last_exc else None, **last_diag,
        },
    )


# ============================================================
# 本地 CLI 调试入口
# ============================================================
if __name__ == "__main__":
    import logging
    from types import SimpleNamespace

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    fake_ctx = SimpleNamespace(
        logger=logging.getLogger("jmcomic-local"),
        timeout_sec=4500, run_id=999, instance_id=999,
        instance_name="local-test", script_slug="jmcomic",
        script_dir=os.path.dirname(os.path.abspath(__file__)),
        data_dir=os.environ.get("JM_DATA_DIR", ""),
        trigger_type="manual", attempt=1, notify=lambda *a, **k: None,
    )
    cfg = {
        "username": os.environ.get("JM_USERNAME", ""),
        "password": os.environ.get("JM_PASSWORD", ""),
        "proxy": os.environ.get("JM_PROXY", ""),
        "random_delay_sec": int(os.environ.get("JM_DELAY", "0") or 0),
        "max_retries": int(os.environ.get("JM_MAX_RETRIES", "3") or 3),
        "retry_interval_sec": int(os.environ.get("JM_RETRY_INTERVAL", "300") or 300),
    }
    result = run(cfg, fake_ctx)
    print("\n========= RESULT =========")
    print(f"success={result.success}")
    print(f"message={result.message}")
    print(f"data={result.data}")
    sys.exit(0 if result.success else 1)
