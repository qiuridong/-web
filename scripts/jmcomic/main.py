"""JMComic(18comic.vip)每日签到 — selenium 账密版(v1.1.0 cookies 复用 + 智能重试)。

改造自 GitHub `huo0yan/JMComic-Auto_Sign_in`,适配本平台 sandbox_runner 协议。

实施原则:
- 完全继承"原脚本"在 host VPS-JM 上的成功经验(2026-04-18 ~ 2026-05-23
  共 33 天 / 33 次 CF Turnstile 全部通过)+ 5-24 v1.0 首跑成功
- 凭证改为账密(`username` + `password`),走 Fernet 加密,Server-side login → cookie 全自动
- 不依赖手工抓 cookie(避免 cookie ↔ 出口 IP 强绑定的部署摩擦)
- 异常体系细化为 7 个子类,失败时 /runs 详情页可见精确诊断
- 兜底:sign 接口空响应时 GET 首页扫 8 个繁简体"已簽到"marker 自救
- **v1.1.0 关键改进**:cookies 复用 + 智能重试 + 仅在 cookies 失效时重过 CF

平台协议要求(对照 backend/sandbox_runner.py):
- 顶级函数 `run(config, context) -> RunResult`
- 不打 ``__RUN_RESULT__``,不 ``sys.exit``(sandbox_runner 负责)
- 账密从 config 拿(已 Fernet 解密)
- 日志用 ``context.logger``,自动汇集到 runs.stdout/stderr
- 失败截图存到 ``context.data_dir``(实例独立目录,持久跨执行)
- 长 sleep 用 `_chunked_sleep`(响应 SIGTERM)

部署要求(重要!):
- 仅在 Linux 节点跑(apt-get / xvfb / Chrome)
- 节点需要 root / sudo(自动装 Chrome、Xvfb 系统包)
- 节点磁盘 ≥ 500 MB(Chrome ~150 MB + chromedriver)
- 节点内存 ≥ 1.5 GB(Chrome 跑时峰值)
- **主面板 Docker 容器不能直接跑此脚本**(需要 MVP-1 远程 agent 派发到 VPS-JM 这类 host Linux 节点)

业务流程(v1.1.0 重构后):
1. _ensure_dependencies — idempotent 装 seleniumbase / xvfbwrapper / requests / xvfb / Chrome / chromedriver
2. _get_cookies_via_browser — Xvfb + SeleniumBase UC 过 CF Turnstile(60-120s,**仅在 cookies 失效时重跑**)
3. _do_login — POST /login 拿 server session(**仅在初次 / cookies 失效时跑**)
4. _do_sign_only — POST /ajax/user_daily_sign(**重试时复用 session,不重 login**)
   - 兜底:GET 首页扫 8 个 marker
   - 检测:`{"msg":""}` 空 msg → JmCookieExpired 触发重新过 CF
5. run() 顶层重试循环:
   - 5 分钟间隔默认(retry_interval_sec)
   - 复用 cookies + session,3 次重试只过 1 次 CF(节省 IP 信任分)
   - 仅在 cookies 失效 / 超 TTL 时才重新过 CF
6. _safe_logout — 安全清场,失败不阻断

历史:
- v1.0.0 (2026-05-23):本版基础,基于 host 33 次验证的 selenium + 账密流程,首次跑 5-24 成功
- v1.1.0 (2026-05-24):cookies 复用 + 智能重试 + CF TTL 自动管理(用户需求:不浪费 CF 信任分)
- v2(已删除,2026-05-23):cookie 复用 + 纯 httpx 版,因 cookie ↔ IP 强绑定废弃
"""
from __future__ import annotations

import importlib
import os
import random
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ============================================================
# 平台协议:RunResult dataclass(sandbox_runner._result_to_dict 兼容)
# ============================================================
@dataclass
class RunResult:
    success: bool
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)


# ============================================================
# 配置(URL 常量,账密走 config 不硬编码)
# ============================================================
LOGIN_URL = "https://18comic.vip/login"
SIGN_URL = "https://18comic.vip/ajax/user_daily_sign"
LOGOUT_URL = "https://18comic.vip/logout"


# ============================================================
# 业务异常 — 精细化分类,每个都带结构化诊断信息
# 历史教训:2026-05-23 server sign 接口对自动化返空响应,原版只笼统抛
# "请求异常: Expecting value: line 1 column 1 (char 0)" 不告诉具体哪个
# 接口 / 什么 status / body 长啥样 → 排查痛苦。现重新设计异常体系:
# 每个异常类带 endpoint / status_code / content_type / body_preview 等。
# ============================================================
class JmError(Exception):
    """JM 业务错误基类。所有子类带结构化诊断字段(data 暴露给 RunResult)。"""

    def __init__(self, message: str, **diag: Any) -> None:
        super().__init__(message)
        self.diag = diag  # 任意诊断字段,RunResult.data 直接展开

    def to_data(self) -> dict[str, Any]:
        """转 RunResult.data 用的 dict,便于在 /runs 详情页看到。"""
        return {"error_class": self.__class__.__name__, **self.diag}


class JmAlreadySignedToday(JmError):
    """server 返回 {"error": ...} 或首页兜底确认今日已签。平台语义 = success。"""


class JmCloudflareBlocked(JmError):
    """5 次重试未过 CF Turnstile。可能 CF 升级 / IP 信任分耗尽 / 同 IP 同天第二次。"""


class JmLoginFailed(JmError):
    """账号 / 密码错误,server 返回 status != 1。无重试价值。"""


class JmCookieExpired(JmError):
    """server 返 anonymous(`{"msg":""}` 空)或 takelogin 表单 — cookies/session 失效。

    触发条件:
      - sign 接口返 `{"msg":""}` 空 msg(server 不认 session)
      - sign 接口返 takelogin HTML 表单(server 主动 logout 了)

    处理:run() 检测到此异常会重新过 CF + 重新 login(消耗 1 次 CF,但必要)。
    """


class JmHttpEndpointError(JmError):
    """HTTP 接口异常基类:非 200 / 空响应 / 非 JSON / 解析失败。

    diag 字段(从 _http_request 收集):
      endpoint        — 'POST /login' / 'POST /sign' / 'GET /index' 等可读标签
      url             — 完整 URL
      status_code     — HTTP 状态码
      content_type    — 响应 Content-Type 头
      content_length  — 响应字节数
      body_preview    — body 前 200 字节(用于诊断,JM 站非敏感 — 不会含 cookie)
      elapsed_ms      — 请求耗时
    """


class JmLoginEndpointError(JmHttpEndpointError):
    """`POST /login` 接口异常(非业务"账密错",而是 HTTP 层异常)。"""


class JmSignEndpointError(JmHttpEndpointError):
    """`POST /ajax/user_daily_sign` 接口异常 — 5-23 事件就是这个。

    典型 5-23 现象:
      status_code = 200
      content_type = "text/html; charset=UTF-8" 或者空
      content_length = 0
      body_preview = "<empty>"
      → server 反爬:登录认它,签到接口对自动化返空
    """


class JmIndexEndpointError(JmHttpEndpointError):
    """`GET /` 兜底接口异常(用来确认是否已签)。"""


class JmNetworkError(JmError):
    """网络层错误(DNS / 连接超时 / TLS 握手失败 / 连接断开)。

    diag 字段:
      endpoint  — 哪个接口
      url       — 完整 URL
      exc_type  — requests 异常类名(ConnectTimeout / SSLError 等)
      elapsed_ms — 失败前耗时
    """


# ============================================================
# 依赖自动安装(idempotent,首次跑约 30s,之后秒过)
# ============================================================
def _ensure_dependencies(logger) -> None:
    """检查 + 自动装:Python 包(seleniumbase / xvfbwrapper / requests)+ apt 系统库 + Chrome + ChromeDriver。"""
    # ---- Python 包 ----
    required_packages = {
        "seleniumbase": "seleniumbase",
        "xvfbwrapper": "xvfbwrapper",
        "requests": "requests",
    }
    missing = [pkg for mod, pkg in required_packages.items() if importlib.util.find_spec(mod) is None]
    if missing:
        logger.info(f"检测到缺失 Python 依赖: {missing},正在自动安装...")
        subprocess.check_call([
            sys.executable, "-m", "pip", "install",
            "--break-system-packages", "--ignore-installed", "--quiet",
            *missing
        ])
        logger.info("Python 依赖安装完成")

    # ---- 系统级依赖(xvfb + Chrome,仅 Linux)----
    if sys.platform.startswith("linux"):
        # 1. Chrome 运行时共享库(idempotent,装过 apt 秒过)
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
        # 2. Google Chrome(不用 chromium,版本可能与 chromedriver 不匹配)
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

    # ---- ChromeDriver(seleniumbase 私有 drivers 目录)----
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
# Xvfb + SeleniumBase UC 过 CF Turnstile,拿 cookies
# ============================================================
def _get_cookies_via_browser(logger, context) -> tuple[dict | None, str | None]:
    """返回 (cookies dict, user_agent str) 或 (None, None) 表示失败。

    依赖:`xvfbwrapper`、`seleniumbase`(由 _ensure_dependencies 保证)。
    失败时把 Chrome 截图存到 context.data_dir/cf_error_<ts>.jpg(若可写)。
    """
    from xvfbwrapper import Xvfb
    from seleniumbase import Driver

    logger.info("启动 Xvfb 虚拟显示器(欺骗 CF 以为有真实屏幕)...")
    vdisplay = Xvfb(width=1280, height=800)
    vdisplay.start()
    os.environ["DISPLAY"] = f":{vdisplay.new_display}"

    logger.info("启动 Chrome UC 模式...")
    driver = Driver(uc=True, headless=False)
    try:
        logger.info(f"访问登录页: {LOGIN_URL}")
        driver.uc_open_with_reconnect(LOGIN_URL, reconnect_time=4)

        def get_cf_clearance() -> str | None:
            for c in driver.get_cookies():
                if c["name"] == "cf_clearance":
                    return c["value"]
            return None

        logger.info("等待 CF 后台完成初始评估(15 秒)...")
        time.sleep(15)

        passed = False
        for attempt in range(5):
            if get_cf_clearance():
                passed = True
                break
            logger.info(f"第 {attempt + 1} 次尝试点击 CF Turnstile...")
            try:
                driver.uc_gui_click_captcha()
            except Exception:
                pass
            time.sleep(6)
            if get_cf_clearance():
                passed = True
                break
            logger.info(f"第 {attempt + 1} 次未获取到 cf_clearance,继续重试...")

        if not passed:
            raise JmCloudflareBlocked("经过 5 次重试仍未获取到 cf_clearance cookie")

        logger.info("✓ CF 验证通过,提取 Cookies 和 UA")
        selenium_cookies = driver.get_cookies()
        cookies = {c["name"]: c["value"] for c in selenium_cookies}
        user_agent = driver.execute_script("return navigator.userAgent")
        logger.info(f"UA: {user_agent[:60]}...")

        driver.quit()
        vdisplay.stop()
        return cookies, user_agent

    except JmCloudflareBlocked:
        # 失败截图存到实例 data_dir
        _try_save_error_screenshot(driver, context, logger)
        try:
            driver.quit()
        except Exception:
            pass
        vdisplay.stop()
        raise
    except Exception as exc:
        logger.error(f"浏览器绕过 CF 异常: {exc}")
        _try_save_error_screenshot(driver, context, logger)
        try:
            driver.quit()
        except Exception:
            pass
        vdisplay.stop()
        raise JmCloudflareBlocked(f"浏览器绕过 CF 异常: {exc}") from exc


def _try_save_error_screenshot(driver, context, logger) -> None:
    """失败截图存到 context.data_dir,失败静默。"""
    try:
        data_dir = getattr(context, "data_dir", "") or ""
        if data_dir:
            ts = int(time.time())
            path = Path(data_dir) / f"cf_error_{ts}.jpg"
            driver.save_screenshot(str(path))
            logger.info(f"失败截图已存: {path}")
    except Exception as exc:
        logger.warning(f"保存失败截图未能完成: {exc}")


# ============================================================
# HTTP helpers — 统一日志 + 结构化诊断
# 5-23 教训:出错时要立刻知道是哪个接口 / status / content-type / body 长啥样
# ============================================================
def _http_request(session, method: str, url: str, label: str, *, logger, **kwargs) -> tuple[Any, dict]:
    """统一 HTTP 调用,返回 (response, diag dict)。

    label 是可读的接口名(如 "POST /login"),用于异常 message 和日志。
    raise JmNetworkError 包装网络层错误(超时 / 连接 / DNS / TLS)。
    """
    import requests as _rq
    start = time.monotonic()
    try:
        r = session.request(method, url, **kwargs)
    except _rq.RequestException as exc:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        logger.error(f"[{label}] {url} 网络错误 ({elapsed_ms}ms): {type(exc).__name__}: {exc}")
        raise JmNetworkError(
            f"[{label}] 网络错误: {type(exc).__name__}: {exc}",
            endpoint=label, url=url, exc_type=type(exc).__name__, elapsed_ms=elapsed_ms,
        ) from exc
    elapsed_ms = int((time.monotonic() - start) * 1000)
    body = r.text or ""
    diag = {
        "endpoint": label,
        "url": url,
        "method": method,
        "status_code": r.status_code,
        "content_type": r.headers.get("Content-Type", ""),
        "content_length": int(r.headers.get("Content-Length", "0") or len(r.content)),
        "elapsed_ms": elapsed_ms,
        "body_preview": (body[:200] if body else "<empty>") if body is not None else "<None>",
        "body_len": len(body),
    }
    logger.info(
        f"[{label}] HTTP {r.status_code} ct={diag['content_type']} "
        f"len={diag['content_length']}B body_len={diag['body_len']} {elapsed_ms}ms"
    )
    return r, diag


def _parse_json_or_raise(response, diag: dict, *, exc_class) -> dict:
    """严格 JSON 解析:非 200 / 空 body / 非 JSON Content-Type / 解析失败 → 精细 raise。

    本函数是 5-23 事件的核心修复 — 把"json.loads 抛笼统 JSONDecodeError"
    改为"按 4 种具体原因分别 raise,带完整 diag 字段"。
    """
    import json as _json
    if response.status_code != 200:
        raise exc_class(
            f"[{diag['endpoint']}] HTTP 非 200(实际 {response.status_code})",
            **diag,
        )
    if not response.text or not response.text.strip():
        raise exc_class(
            f"[{diag['endpoint']}] 响应 body 为空(status=200,ct={diag['content_type']!r},"
            f"len={diag['content_length']}B)— 疑似 server 反爬静默拒绝",
            **diag,
        )
    ct_lower = (diag.get("content_type") or "").lower()
    if "json" not in ct_lower and not response.text.lstrip().startswith(("{", "[")):
        raise exc_class(
            f"[{diag['endpoint']}] 响应非 JSON(Content-Type={diag['content_type']!r}),"
            f"body 前 200: {diag['body_preview']!r}",
            **diag,
        )
    try:
        return _json.loads(response.text)
    except _json.JSONDecodeError as exc:
        raise exc_class(
            f"[{diag['endpoint']}] JSON 解析失败 ({exc}),"
            f"ct={diag['content_type']!r}, body 前 200: {diag['body_preview']!r}",
            **diag,
        ) from exc


def _check_already_signed_via_index(session, headers: dict, logger) -> tuple[bool, dict]:
    """sign 接口异常时的兜底:GET 首页看用户区是否有"已簽到"标志。

    返回 (是否已签, diag dict)。
    JM (NexusPHP / 自定义) 用户首页含繁体中文"今日簽到"/"已簽到"等标记 →
    认为是已签状态(server 实际签了,只是 sign 接口对自动化静默拒)。
    """
    try:
        r, diag = _http_request(session, "GET", "https://18comic.vip/", "GET / (兜底)", logger=logger, headers=headers, timeout=20)
    except JmNetworkError as exc:
        logger.warning(f"兜底首页 GET 网络失败(忽略,按未签处理): {exc}")
        return False, {}
    text = r.text or ""
    # JM 18comic 首页登录态可能的"今日已签"标记词(覆盖繁简体)
    markers = (
        "今日已簽到", "已簽到", "今日已签到", "已签到",
        "已经签到", "已經簽到", "您已簽到", "您已签到",
    )
    for marker in markers:
        if marker in text:
            logger.info(f"✓ 兜底:首页含 '{marker}' = 今日已签到")
            return True, {**diag, "matched_marker": marker}
    # 没匹配到 — 看是否登录态(应当含 logout 链接或用户名链接)
    if "logout" in text.lower() or "登出" in text or "userdetails.php" in text:
        logger.info("兜底:首页是登录态但无'已签'标记 → 未签")
    else:
        logger.warning("兜底:首页不像登录态(无 logout / 用户区) → 状态不确定,按未签处理")
    return False, diag


# ============================================================
# 登录(只登录,返回 session 给后续 sign 复用)
# v1.1.0 改:从 _do_sign_in 拆出来,让 session 可在 retry 时复用
# ============================================================
def _do_login(cookies: dict, user_agent: str, username: str, password: str, logger) -> Any:
    """用 CF cookies 启动 session,POST /login 登录,返回带 server session 的 requests.Session。

    后续 sign 调用复用此 session(不再重复 login)。

    raise:
      - JmLoginEndpointError — login HTTP/解析层异常
      - JmLoginFailed        — server 返 status!=1(账密错,**不重试**)
      - JmNetworkError       — 网络层
    """
    import requests

    headers = {
        "User-Agent": user_agent,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Referer": LOGIN_URL,
        "Origin": "https://18comic.vip",
    }
    payload = {"username": username, "password": password, "submit_login": "1"}

    session = requests.Session()
    requests.utils.add_dict_to_cookiejar(session.cookies, cookies)

    login_resp, login_diag = _http_request(
        session, "POST", LOGIN_URL, "POST /login",
        logger=logger, data=payload, headers=headers, timeout=30,
    )
    login_data = _parse_json_or_raise(login_resp, login_diag, exc_class=JmLoginEndpointError)
    if login_data.get("status") != 1:
        raise JmLoginFailed(
            f"登录失败: {login_data.get('errors', '未知错误')}",
            endpoint=login_diag["endpoint"], status=login_data.get("status"),
            errors=login_data.get("errors"),
        )
    logger.info("✓ login 业务成功 (status=1)")
    # 把 ua 存到 session.headers 让后续 sign 自动带
    session.headers.update({"User-Agent": user_agent})
    return session


# ============================================================
# 签到(只 sign,复用已 login 的 session)
# v1.1.0 改:从 _do_sign_in 拆出来,可在 retry 时只重 sign 不重 login
# ============================================================
def _do_sign_only(session: Any, user_agent: str, logger) -> dict[str, Any]:
    """用现成 session(已 login)调一次 sign + 兜底 marker。

    return: {"msg": ..., "raw_resp": ..., "sign_diag": ...}

    raise:
      - JmSignEndpointError  — sign HTTP/解析层异常(可重试 sign,不重 login)
      - JmAlreadySignedToday — server 已签
      - **JmCookieExpired**  — server 返 `{"msg":""}` 空 = session 失效(需重 CF + 重 login)
      - JmNetworkError
    """
    headers = {
        "User-Agent": user_agent,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Referer": LOGIN_URL,
        "Origin": "https://18comic.vip",
    }

    sign_resp, sign_diag = _http_request(
        session, "POST", SIGN_URL, "POST /ajax/user_daily_sign",
        logger=logger, headers={**headers, "X-Requested-With": "XMLHttpRequest"}, timeout=30,
    )
    try:
        sign_data = _parse_json_or_raise(sign_resp, sign_diag, exc_class=JmSignEndpointError)
    except JmSignEndpointError as exc:
        # 5-23 事件兜底:sign 接口空 / 非 JSON 时,GET 首页确认是否已签
        logger.warning(f"sign 接口异常,启动兜底首页检查: {exc}")
        already_signed, index_diag = _check_already_signed_via_index(session, headers, logger)
        if already_signed:
            raise JmAlreadySignedToday(
                f"sign 接口异常但首页确认今日已签 (fallback via /). "
                f"sign 接口诊断: {exc}",
                fallback="index_marker",
                sign_diag=exc.diag,
                index_diag=index_diag,
            )
        # 兜底也认未签 → 让 sign endpoint 错误冒泡(可重试 sign)
        raise

    # 业务层判定:server 返 {"error": ...} = 已签
    if "error" in sign_data:
        logger.info(f"server 业务返回已签状态: {sign_data}")
        raise JmAlreadySignedToday(
            str(sign_data.get("error") or "今日已签到过了"),
            fallback="sign_endpoint_error_field",
            sign_data=sign_data,
            sign_diag=sign_diag,
        )

    # 检测 anonymous(cookies/session 失效):{"msg": ""} 或 msg 缺失
    msg = sign_data.get("msg", "")
    if msg is None or not str(msg).strip():
        raise JmCookieExpired(
            f"sign 接口返 anonymous(msg 为空) — cookies/session 已失效,需要重新过 CF + login",
            sign_data=sign_data,
            sign_diag=sign_diag,
        )

    # 真成功
    logger.info(f"✓ 签到成功: {msg}")
    return {"msg": msg, "raw_resp": sign_data, "sign_diag": sign_diag}


def _safe_logout(session, headers: dict, logger) -> None:
    """logout 尽量做,失败不抛(不影响主业务)。"""
    try:
        session.get(LOGOUT_URL, headers=headers, timeout=15)
        logger.info("✓ logout 已尝试")
    except Exception as exc:
        logger.warning(f"logout 阶段异常(忽略): {exc}")


# ============================================================
# 平台基础:分块 sleep(支持响应 SIGTERM)
# ============================================================
def _chunked_sleep(total_sec: int, chunk: int = 30) -> None:
    """分块 sleep,降低长延迟期间无法响应中断的风险。

    主程序 SIGTERM 时(用户点取消 / 实例 timeout 触发),Python 默认
    `time.sleep(N)` 整段无法响应,要等满 N 秒。改用 30 秒 chunk 后,
    一次 SIGTERM 最多在 30 秒内被识别 + 进入 cleanup。
    """
    remaining = total_sec
    while remaining > 0:
        time.sleep(min(chunk, remaining))
        remaining -= chunk


# ============================================================
# 平台主入口(v1.1.0 重构:cookies 复用 + 智能重试 + CF TTL 管理)
# ============================================================
def run(config: dict, context: Any) -> RunResult:
    logger = context.logger
    username = (config.get("username") or "").strip()
    password = (config.get("password") or "").strip()
    delay = int(config.get("random_delay_sec", 0) or 0)
    max_retries = int(config.get("max_retries", 3) or 3)
    retry_interval = int(config.get("retry_interval_sec", 300) or 300)  # 默认 5 分钟
    cf_ttl = int(config.get("cf_clearance_ttl_sec", 1800) or 1800)  # 默认 30 分钟

    # 1) 字段校验
    if not username or not password:
        logger.error("username 或 password 字段为空")
        return RunResult(
            success=False,
            message="username 或 password 字段为空,请到实例配置补全",
        )

    # 2) 随机延迟 + sanity check
    # ⭐ 立即运行(用户手动触发)跳过 random_delay — "立即"就该立即,不等
    trigger_type = str(getattr(context, "trigger_type", "scheduled") or "scheduled")
    if trigger_type == "manual" and delay > 0:
        logger.info(
            f"trigger_type=manual(用户立即触发)→ 跳过 random_delay({delay}s)立即开始"
        )
        delay = 0
    # 估算:首次 CF 60-120s + login 1s + sign 1s + N-1 次重试间隔(可能含 cf 重过)
    instance_timeout = int(getattr(context, "timeout_sec", 0) or 0)
    estimated_budget = 180 + (max_retries - 1) * retry_interval
    safe_budget = max(0, instance_timeout - estimated_budget)
    if instance_timeout > 0 and delay > safe_budget:
        original = delay
        delay = safe_budget
        logger.warning(
            f"random_delay_sec={original} > 实例 timeout({instance_timeout}) - 预估业务耗时({estimated_budget}),"
            f"会被超时强杀。临时 cap 到 {delay}s。"
            f"建议:实例 timeout_sec 调到 ≥ {original + estimated_budget}。"
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

    # 3) 依赖检查(idempotent)
    try:
        _ensure_dependencies(logger)
    except subprocess.CalledProcessError as exc:
        logger.error(f"依赖安装失败: {exc}")
        return RunResult(
            success=False,
            message=f"依赖安装失败(可能权限不足或网络问题): {exc}",
        )

    # 4) cookies/session 生命周期管理变量
    cookies: dict | None = None
    user_agent: str | None = None
    session: Any | None = None
    cf_obtained_at: float | None = None

    def refresh_cf_and_login() -> None:
        """重新过 CF + 重新 login(消耗 1 次 CF 信任分,只在必要时调用)。

        更新外层 cookies / user_agent / session / cf_obtained_at。
        失败 raise(让外层 catch)。
        """
        nonlocal cookies, user_agent, session, cf_obtained_at
        c, ua = _get_cookies_via_browser(logger, context)
        if not c or not ua:
            raise JmCloudflareBlocked("未能拿到 CF 合法 cookies")
        cookies = c
        user_agent = ua
        session = _do_login(cookies, user_agent, username, password, logger)
        cf_obtained_at = time.monotonic()

    # 5) 初次过 CF + login(失败立即返失败,不重试)
    try:
        refresh_cf_and_login()
    except JmCloudflareBlocked as exc:
        logger.error(f"初次过 CF 失败: {exc}")
        return RunResult(
            success=False,
            message=str(exc),
            data={"category": "cf_blocked_initial", **exc.to_data()},
        )
    except JmLoginFailed as exc:
        logger.error(f"账密错误,无需重试: {exc}")
        return RunResult(
            success=False,
            message=str(exc),
            data={"category": "login_failed", **exc.to_data()},
        )
    except (JmLoginEndpointError, JmNetworkError) as exc:
        logger.error(f"初次 login 接口异常: {exc}")
        return RunResult(
            success=False,
            message=str(exc),
            data={"category": "initial_login_endpoint_error", **exc.to_data()},
        )
    except Exception as exc:
        logger.exception(f"初次过 CF + login 未知异常: {type(exc).__name__}")
        return RunResult(
            success=False,
            message=f"初次过 CF + login 未知异常: {type(exc).__name__}: {exc}",
            data={"category": "initial_unknown_error", "error_class": type(exc).__name__},
        )

    logger.info(
        f"✓ 初次过 CF + login 完成,cookies 有效期保守值 {cf_ttl}s "
        f"(retry={max_retries} 次,间隔 {retry_interval}s)"
    )

    # 6) 重试循环 — 复用 cookies/session,智能重过 CF
    last_exc: Exception | None = None

    for attempt in range(1, max_retries + 1):
        logger.info(f"========= 第 {attempt}/{max_retries} 次签到尝试 =========")

        # 检查 cookies TTL — 超时主动重过 CF(预防性)
        elapsed = int(time.monotonic() - cf_obtained_at)
        if elapsed > cf_ttl:
            logger.info(f"cf_clearance 已用 {elapsed}s > 配置 ttl({cf_ttl}s),主动重新过 CF + login")
            try:
                refresh_cf_and_login()
            except Exception as exc:
                logger.error(f"重新过 CF + login 失败: {exc}")
                last_exc = exc
                if attempt < max_retries:
                    _chunked_sleep(retry_interval)
                continue

        try:
            data = _do_sign_only(session, user_agent, logger)
            # 成功 — logout 后返
            _safe_logout(session, {"User-Agent": user_agent, "Referer": LOGIN_URL}, logger)
            return RunResult(
                success=True,
                message=f"签到成功: {data.get('msg', '')}",
                data={
                    "category": "signed_now",
                    "attempt": attempt,
                    "cookies_age_sec": int(time.monotonic() - cf_obtained_at),
                    **data,
                },
            )
        except JmAlreadySignedToday as exc:
            # 已签到 — 平台语义 = success
            _safe_logout(session, {"User-Agent": user_agent, "Referer": LOGIN_URL}, logger)
            return RunResult(
                success=True,
                message=f"今日已签到过了: {exc}",
                data={"category": "already_signed_today", "attempt": attempt, **exc.to_data()},
            )
        except JmCookieExpired as exc:
            # cookies 失效 — 重新过 CF + login(消耗 1 次,必要)
            logger.warning(f"第 {attempt} 次:cookies/session 失效({exc}),重新过 CF + login")
            last_exc = exc
            try:
                refresh_cf_and_login()
                logger.info("✓ 重新过 CF + login 完成,下一轮立即试 sign(不等 retry_interval)")
                # 立即下一轮(不 sleep) — 因为 cookies 刚刷,服务器应当认
            except Exception as exc2:
                logger.error(f"重新过 CF + login 也失败: {exc2}")
                last_exc = exc2
                if attempt < max_retries:
                    _chunked_sleep(retry_interval)
        except JmSignEndpointError as exc:
            # sign HTTP 层错(5-23 类) — 业务层重试(复用 cookies + session,不重 CF)
            last_exc = exc
            logger.error(f"第 {attempt} 次 sign 接口异常: {exc}")
            if attempt < max_retries:
                logger.info(f"将在 {retry_interval} 秒后重试(复用 cookies/session,不重新过 CF)...")
                _chunked_sleep(retry_interval)
        except JmNetworkError as exc:
            # 网络层 — 业务层重试
            last_exc = exc
            logger.error(f"第 {attempt} 次网络错误: {exc}")
            if attempt < max_retries:
                logger.info(f"将在 {retry_interval} 秒后重试...")
                _chunked_sleep(retry_interval)
        except JmError as exc:
            # 其它 JM 业务错误(基类兜底)
            last_exc = exc
            logger.error(f"第 {attempt} 次 JM 业务错误: {exc}")
            if attempt < max_retries:
                _chunked_sleep(retry_interval)
        except Exception as exc:
            # 完全未知异常 — 给 stack trace
            last_exc = exc
            logger.exception(f"第 {attempt} 次未知异常 ({type(exc).__name__})")
            if attempt < max_retries:
                _chunked_sleep(retry_interval)

    # 7) 重试用尽 — safe logout + 返失败
    if session is not None:
        _safe_logout(session, {"User-Agent": user_agent or "", "Referer": LOGIN_URL}, logger)

    last_diag: dict[str, Any] = {}
    if isinstance(last_exc, JmError):
        last_diag = last_exc.to_data()
    elif last_exc is not None:
        last_diag = {"error_class": type(last_exc).__name__}

    return RunResult(
        success=False,
        message=f"已达到最大重试次数 {max_retries},最后错误: {last_exc}",
        data={
            "category": "exhausted_retries",
            "max_retries": max_retries,
            "retry_interval_sec": retry_interval,
            "cf_clearance_ttl_sec": cf_ttl,
            "final_cookies_age_sec": int(time.monotonic() - cf_obtained_at) if cf_obtained_at else None,
            "last_error_repr": repr(last_exc) if last_exc else None,
            **last_diag,
        },
    )


# ============================================================
# 本地 CLI 调试入口(不经过 sandbox_runner 时用)
# ============================================================
if __name__ == "__main__":
    """
    本地跑(Linux,需 root 装 apt + Chrome):
      export JM_USERNAME=xxx
      export JM_PASSWORD=yyy
      export JM_DELAY=0              # 测试时不延迟
      export JM_MAX_RETRIES=3
      export JM_RETRY_INTERVAL=300   # 5 分钟
      export JM_CF_TTL=1800          # 30 分钟
      python3 main.py
    """
    import logging
    from types import SimpleNamespace

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    fake_ctx = SimpleNamespace(
        logger=logging.getLogger("jmcomic-local"),
        timeout_sec=4500,
        run_id=0,
        instance_id=0,
        instance_name="local-test",
        script_slug="jmcomic",
        script_dir=os.path.dirname(os.path.abspath(__file__)),
        data_dir=os.environ.get("JM_DATA_DIR", ""),
        trigger_type="manual",
        attempt=1,
        notify=lambda *a, **k: None,
    )
    cfg = {
        "username": os.environ.get("JM_USERNAME", ""),
        "password": os.environ.get("JM_PASSWORD", ""),
        "random_delay_sec": int(os.environ.get("JM_DELAY", "0") or 0),
        "max_retries": int(os.environ.get("JM_MAX_RETRIES", "3") or 3),
        "retry_interval_sec": int(os.environ.get("JM_RETRY_INTERVAL", "300") or 300),
        "cf_clearance_ttl_sec": int(os.environ.get("JM_CF_TTL", "1800") or 1800),
    }
    result = run(cfg, fake_ctx)
    print(f"\n========= RESULT =========")
    print(f"success={result.success}")
    print(f"message={result.message}")
    print(f"data={result.data}")
    sys.exit(0 if result.success else 1)
