"""COKLW 每日签到 — https://coklw.net/

实现方案:用户提供已登录 cookie,脚本走 WordPress admin-ajax.php 接口
1. 调状态接口(action=a1695e2e97b11317858156779ec6ab41,带子查询 checkSigned)
   → 拿响应顶层 `_nonce` + `customPointSignDaily.signed`
2. 若已签到(`signed === True`),直接返回 success
3. 否则用 nonce 调签到接口
   GET /wp-admin/admin-ajax.php?_nonce=<n>&action=07e2fafdb61c964ff31938b1ac72ace4&type=goSign
4. code==0 + msg 含"签到" → success;否则 failure

签到 action hash / 状态 action hash / 子查询格式 全部从 HAR 真实抓包提取。

主程序契约:见 `进度/设计/后端架构.md` § 3.3。
本文件可独立用 `python main.py` 测试,见底部 __main__ 块。
"""
from __future__ import annotations

import json
import logging
import os
import random
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Any

import httpx

# ---------------------------------------------------------------------------
# 接口常量(从 HAR 真实抓包提取)
# ---------------------------------------------------------------------------

BASE_URL = "https://coklw.net"
AJAX_PATH = "/wp-admin/admin-ajax.php"

# 状态聚合接口的外层 action hash
STATUS_ACTION = "a1695e2e97b11317858156779ec6ab41"

# 子查询:检查"今日是否已签到" — 由签到 action 自身用 batch 形式调用
SIGN_ACTION = "07e2fafdb61c964ff31938b1ac72ace4"
CHECK_SIGNED_TYPE = "checkSigned"
GO_SIGN_TYPE = "goSign"

# 签到响应里 msg 中包含以下任一字样视为成功
SUCCESS_MSG_KEYWORDS = ("签到", "勇士", "已签", "成功")

# WordPress logged-in cookie 名前缀(后接 32 位 COOKIEHASH,因站点配置而异)
LOGGED_IN_COOKIE_PREFIX = "wordpress_logged_in_"


# ---------------------------------------------------------------------------
# RunResult — 与主程序 sandbox runner 协议一致
# ---------------------------------------------------------------------------

@dataclass
class RunResult:
    success: bool
    message: str = ""
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# 自定义异常
# ---------------------------------------------------------------------------

class CoklwError(Exception):
    """脚本可识别的业务异常,会被转成 RunResult.failure 而非 error。"""


class CookieMissingError(CoklwError):
    """cookie 字段为空 / 缺关键 wordpress_logged_in_* 项。"""


class NotLoggedInError(CoklwError):
    """状态接口返回未登录(无 user 字段),通常是 cookie 过期。"""


class NonceMissingError(CoklwError):
    """状态接口响应中没有 _nonce 字段,可能站点改版或被风控。"""


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _validate_cookie(cookie: str) -> None:
    """简单校验 cookie 字符串是否包含 wordpress_logged_in_* 项。"""
    if not cookie or not cookie.strip():
        raise CookieMissingError("Cookie 字段为空,请按字段说明从浏览器复制 cookie 字符串")
    # 不要求一定有 LOGGED_IN_COOKIE_PREFIX(用户可能只复制了 sec_),只 warn 不抛
    # —— 其实为可靠性,这里抛一下,因为没这个签到几乎必失败
    if LOGGED_IN_COOKIE_PREFIX not in cookie:
        raise CookieMissingError(
            f"Cookie 字符串中未找到 `{LOGGED_IN_COOKIE_PREFIX}*=...` 项,"
            "请确保从浏览器复制了登录后的 cookie(典型有效期 14 天)"
        )


def _build_status_query() -> str:
    """构造状态接口 query string(WordPress batch 调用格式)。

    形如:
      action=a1695e2e97b11317858156779ec6ab41
      &07e2fafdb61c964ff31938b1ac72ace4[type]=checkSigned
    """
    # action= 是顶层路由;子查询 hash[type]=name 告诉聚合 endpoint 调哪个子动作
    # 这里只挂 checkSigned 一个子查询,响应足以拿到 _nonce + signed
    inner_key = f"{SIGN_ACTION}[type]"
    # 注意:httpx 会自动 url-encode,这里 [ ] 会被编码成 %5B %5D,与浏览器一致
    return f"?action={STATUS_ACTION}&{inner_key}={CHECK_SIGNED_TYPE}"


def _is_signed(status_json: dict) -> bool | None:
    """判断状态响应里今日是否已签到。

    返回 True/False/None(None = 字段缺失,无法判断)。
    """
    daily = status_json.get("customPointSignDaily")
    if not isinstance(daily, dict):
        return None
    return bool(daily.get("signed"))


def _is_logged_in(status_json: dict) -> bool:
    """状态响应里有 user.name 字段即视为已登录。"""
    user = status_json.get("user")
    return isinstance(user, dict) and bool(user.get("name"))


def _success_msg_match(msg: str) -> bool:
    return any(kw in msg for kw in SUCCESS_MSG_KEYWORDS)


# ---------------------------------------------------------------------------
# HTTP 调用
# ---------------------------------------------------------------------------

def fetch_status(client: httpx.Client, logger: logging.Logger) -> dict:
    """调状态接口,返回完整 JSON。同时验证已登录态 + 拿 _nonce。"""
    url = f"{BASE_URL}{AJAX_PATH}{_build_status_query()}"
    logger.debug(f"GET status {url}")
    r = client.get(url)
    if r.status_code != 200:
        raise CoklwError(
            f"状态接口 HTTP {r.status_code}: {r.text[:200]}"
        )
    try:
        data = r.json()
    except ValueError as e:
        raise CoklwError(f"状态接口返回非 JSON: {e}; body 头部: {r.text[:200]!r}")

    if not _is_logged_in(data):
        raise NotLoggedInError(
            "状态接口未返回用户信息,cookie 可能已过期 — 请重新登录 coklw.net 复制 cookie"
        )
    if not data.get("_nonce"):
        raise NonceMissingError("状态接口响应中没有 _nonce 字段(站点可能改版)")
    return data


def do_sign(client: httpx.Client, nonce: str, logger: logging.Logger) -> dict:
    """调签到接口,返回完整 JSON。"""
    url = (
        f"{BASE_URL}{AJAX_PATH}"
        f"?_nonce={nonce}&action={SIGN_ACTION}&type={GO_SIGN_TYPE}"
    )
    logger.debug(f"GET sign  {url}")
    r = client.get(url)
    if r.status_code != 200:
        raise CoklwError(
            f"签到接口 HTTP {r.status_code}: {r.text[:300]}"
        )
    try:
        data = r.json()
    except ValueError as e:
        raise CoklwError(f"签到接口返回非 JSON: {e}; body 头部: {r.text[:200]!r}")
    return data


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def run(config: dict, context: Any) -> RunResult:
    logger: logging.Logger = context.logger
    cookie = (config.get("cookie") or "").strip()
    delay = int(config.get("random_delay_sec", 0) or 0)
    ua = (
        config.get("user_agent")
        or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0"
    )
    skip_if_signed = bool(config.get("skip_if_signed", True))

    # 1) cookie 基本校验
    try:
        _validate_cookie(cookie)
    except CookieMissingError as e:
        logger.error(f"Cookie 校验失败: {e}")
        return RunResult(success=False, message=str(e))

    # 2) 随机延迟(避开固定时刻被识别为机器人)
    # ⚠️ Sanity check:防止 delay > timeout_sec - 60 → 必被主程序 SIGTERM 杀掉
    # 实际签到约需 5-15s,留 60s 余量足够;cap 后 warn 提示用户调实例 timeout
    instance_timeout = int(getattr(context, "timeout_sec", 0) or 0)
    if instance_timeout > 0 and delay > instance_timeout - 60:
        original_delay = delay
        delay = max(0, instance_timeout - 60)
        logger.warning(
            f"random_delay_sec={original_delay} > 实例 timeout({instance_timeout}s) - 60,"
            f"会被主程序超时强杀。已临时 cap 到 {delay}s。"
            f"建议把实例 timeout_sec 调到 ≥ {original_delay + 60} 或减小 random_delay。"
        )

    if delay > 0:
        sleep_sec = random.randint(0, delay)
        if sleep_sec > 0:
            logger.info(
                f"随机延迟 {sleep_sec} 秒后开始签到(配置上限 {delay}s)..."
            )
            # 长延迟期间用 chunked sleep,便于上层可捕获 SIGTERM 中断
            _chunked_sleep(sleep_sec)
        else:
            logger.info("随机延迟掷骰得 0 秒,立即开始签到")
    else:
        logger.info("随机延迟禁用,立即开始签到")

    headers = {
        "User-Agent": ua,
        "Referer": f"{BASE_URL}/",
        "Origin": BASE_URL,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "X-Requested-With": "XMLHttpRequest",
        "Cookie": cookie,
    }

    # HTTP 超时:留 10s 余量给主程序的整体 timeout_sec
    http_timeout = max(10, min(int(getattr(context, "timeout_sec", 30)) - 10, 60))

    try:
        with httpx.Client(
            headers=headers,
            follow_redirects=True,
            timeout=http_timeout,
            http2=False,  # 避免 cloudflare 偶发 H2 SETTINGS 异常
        ) as client:
            # 3) 拉状态 + 拿 nonce
            status = fetch_status(client, logger)
            nonce = status["_nonce"]
            user_name = (status.get("user") or {}).get("name") or "<unknown>"
            point = (status.get("user") or {}).get("point")
            logger.info(f"已登录: {user_name} (积分={point}, nonce={nonce[:8]}...)")

            signed_now = _is_signed(status)
            if signed_now is True and skip_if_signed:
                logger.info("状态接口显示今日已签到,跳过签到请求")
                return RunResult(
                    success=True,
                    message="今日已签到(状态接口确认)",
                    data={
                        "already_signed": True,
                        "user": user_name,
                        "point": point,
                    },
                )
            if signed_now is None:
                logger.warning(
                    "状态接口未返回 customPointSignDaily 字段,无法预判;直接尝试签到"
                )

            # 4) 调签到
            sign_resp = do_sign(client, nonce, logger)
            code = sign_resp.get("code")
            msg = sign_resp.get("msg") or ""
            logger.info(f"签到接口响应: code={code}, msg={msg!r}")

            if code == 0 and _success_msg_match(msg):
                return RunResult(
                    success=True,
                    message=msg or "签到成功",
                    data={
                        "already_signed": False,
                        "user": user_name,
                        "point": point,
                        "response": sign_resp,
                    },
                )

            # code==0 但 msg 含"已签到"也算成功(防御性)
            if code == 0 and ("已签" in msg or "签过" in msg):
                return RunResult(
                    success=True,
                    message=msg or "今日已签到",
                    data={
                        "already_signed": True,
                        "user": user_name,
                        "point": point,
                        "response": sign_resp,
                    },
                )

            # 其余 code != 0 或 msg 异常
            return RunResult(
                success=False,
                message=f"签到失败: code={code}, msg={msg!r}",
                data={"response": sign_resp},
            )

    except CoklwError as e:
        # 已知业务错误,转成 RunResult.failure 不抛异常
        logger.error(f"业务错误: {e}")
        return RunResult(success=False, message=str(e))
    except httpx.HTTPError as e:
        logger.error(f"网络错误: {type(e).__name__}: {e}")
        return RunResult(
            success=False,
            message=f"网络错误({type(e).__name__}): {e}",
        )
    # 其余意外异常不捕获,让 sandbox runner 转成 status=error


def _chunked_sleep(total_sec: int, chunk: int = 30) -> None:
    """分块 sleep,降低长延迟期间无法响应中断的风险。"""
    remaining = total_sec
    while remaining > 0:
        time.sleep(min(chunk, remaining))
        remaining -= chunk


# ---------------------------------------------------------------------------
# 本地独立测试入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    """用法:
        # 推荐:把 cookie 放环境变量,避免命令行历史泄漏
        $env:COKLW_COOKIE="wordpress_logged_in_xxx=yyy; wordpress_sec_xxx=zzz"
        python main.py

        # 或者直接给完整 JSON config(覆盖所有字段):
        $env:COKLW_CONFIG='{"cookie":"...","random_delay_sec":0,"skip_if_signed":true}'
        python main.py
    """
    logging.basicConfig(
        level=logging.DEBUG if os.environ.get("COKLW_DEBUG") else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    @dataclass
    class _LocalContext:
        run_id: int = 0
        instance_id: int = 0
        instance_name: str = "local-test"
        script_slug: str = "coklw"
        script_dir: str = os.path.dirname(os.path.abspath(__file__))
        data_dir: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_local_data")
        timeout_sec: int = 60
        trigger_type: str = "manual"
        attempt: int = 1
        logger: logging.Logger = field(default_factory=lambda: logging.getLogger("coklw"))

        def notify(self, title: str, body: str = "", level: str = "info") -> None:
            self.logger.info(f"[notify {level}] {title}: {body}")

    # 加载 config:优先 COKLW_CONFIG(JSON),否则用零散环境变量拼一个
    raw_cfg = os.environ.get("COKLW_CONFIG")
    if raw_cfg:
        try:
            cfg = json.loads(raw_cfg)
        except json.JSONDecodeError as e:
            print(f"COKLW_CONFIG 不是合法 JSON: {e}", file=sys.stderr)
            sys.exit(2)
    else:
        cfg = {
            "cookie": os.environ.get("COKLW_COOKIE", ""),
            "random_delay_sec": int(os.environ.get("COKLW_DELAY", "0") or 0),
            "skip_if_signed": os.environ.get("COKLW_SKIP_IF_SIGNED", "1") not in ("0", "false", "False"),
        }
        if os.environ.get("COKLW_UA"):
            cfg["user_agent"] = os.environ["COKLW_UA"]

    ctx = _LocalContext()
    os.makedirs(ctx.data_dir, exist_ok=True)

    print("=" * 60, file=sys.stderr)
    print(f"COKLW 签到 · 本地测试 · script_dir={ctx.script_dir}", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    result = run(cfg, ctx)
    out = json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
    print(out)
    sys.exit(0 if result.success else 1)
