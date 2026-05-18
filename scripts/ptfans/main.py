"""PTFans 每日签到 — https://ptfans.cc/

实现方案:用户提供已登录 cookie(`c_secure_pass`),脚本走 NexusPHP 标准签到流程。

流程
----
1. GET `/index.php` —— 读用户名 + 顶部 `[签到已得 X]` 或 `[签到得魔力]` 文本
   - 已签到当天显示 `[签到已得 X, 补签卡: Y]` → 跳过(若 skip_if_signed=true)
   - 未签到显示 `[签到得魔力]` → 继续到第 2 步
2. GET `/attendance.php` —— NexusPHP 此请求即完成今日签到
   - 响应主体含 `<h2>签到成功</h2>` + `本次签到获得 <b>N</b> 个魔力值` → success
   - 响应主体含 `<h2>签到失败</h2>` 或其它错误 → failure(透传 HTML 摘录)
3. 解析连续签到天数 + 排名 + 总次数填入 RunResult.data

接口常量从 HAR(`D:\\PTFans.har`)实抓提取。

主程序契约:见 `进度/设计/后端架构.md` § 3.3;
本文件可独立用 `python main.py` 测试,见底部 `__main__` 块。
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

BASE_URL = "https://ptfans.cc"
INDEX_PATH = "/index.php"
ATTENDANCE_PATH = "/attendance.php"

# 必需 cookie 名(NexusPHP 登录态核心 cookie)
REQUIRED_COOKIE = "c_secure_pass"

# HTML 解析模式 ——
# 顶部用户区已签 / 未签的链接文本
RE_SIGNED_TODAY = re.compile(
    r'<a[^>]*href="attendance\.php"[^>]*>\s*\[签到已得\s*([\d.]+)[^]]*\]\s*</a>',
    re.IGNORECASE,
)
RE_NOT_SIGNED = re.compile(
    r'<a[^>]*href="attendance\.php"[^>]*>\s*\[签到得魔力\]\s*</a>',
    re.IGNORECASE,
)
# attendance.php 响应:签到成功 H2 + 主体段
RE_SIGN_OK_H2 = re.compile(r'<h2[^>]*>\s*签到成功\s*</h2>', re.IGNORECASE)
RE_SIGN_FAIL_H2 = re.compile(r'<h2[^>]*>\s*签到失败\s*</h2>', re.IGNORECASE)
RE_GAIN_BONUS = re.compile(
    r'本次签到获得\s*<b[^>]*>\s*([\d.]+)\s*</b>\s*个魔力值',
    re.IGNORECASE,
)
RE_TOTAL_TIMES = re.compile(
    r'这是您的第\s*<b[^>]*>\s*(\d+)\s*</b>\s*次签到',
    re.IGNORECASE,
)
RE_CONTINUOUS_DAYS = re.compile(
    r'已连续签到\s*<b[^>]*>\s*(\d+)\s*</b>\s*天',
    re.IGNORECASE,
)
RE_TODAY_RANK = re.compile(
    r'今日签到排名[:：]\s*<b[^>]*>\s*(\d+)\s*</b>',
    re.IGNORECASE,
)
# 顶部用户区(用于 _parse_user_info 抽用户名;基于 HAR 样本,可能某些主题不匹配)
RE_USERNAME = re.compile(
    r'href="[^"]*userdetails\.php\?id=(\d+)[^"]*"[^>]*class="?User_Name"?[^>]*>\s*<b>([^<]+)</b>',
    re.IGNORECASE,
)
RE_BONUS_VALUE = re.compile(
    r"魔力值\s*</font>\s*\[<a[^>]*>使用</a>\]\s*[:：]?\s*([\d.,]+)",
    re.IGNORECASE,
)
# 2026-05-18 hotfix:登录态宽松判定。
# 原因:RE_USERNAME 太严格(必须 class="User_Name"),不同 NexusPHP 主题
#       (BambooGreen 等)用的 class 名不一样 → 已登录页面被误判为未登录。
# 修法:只要含 userdetails.php?id=<数字> 或 logout 链接 = 登录态信号。
#       PT 站首页通常没指向"其它用户"的 userdetails 链接,该判定足够准确。
RE_LOGGED_IN_HINT = re.compile(
    r'(href="[^"]*userdetails\.php\?id=\d+|href="[^"]*logout\.php)',
    re.IGNORECASE,
)
# 未登录态(NexusPHP 通常会跳到 login.php 或显示 takelogin 表)
RE_LOGIN_FORM = re.compile(
    r'<form[^>]*action\s*=\s*"[^"]*takelogin\.php"',
    re.IGNORECASE,
)

# 已签到 message 关键词(防御性:即便走到 attendance.php 也可能返回"今日已签")
SIGNED_ALREADY_KEYWORDS = (
    "您今天已经签过到了",
    "您今天已签到",
    "今天已签到",
    "您已签到",
    "已经签过到了",
)


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

class PTFansError(Exception):
    """脚本可识别的业务异常,会被转成 RunResult.failure。"""


class CookieMissingError(PTFansError):
    """cookie 字段为空 / 缺关键 c_secure_pass。"""


class NotLoggedInError(PTFansError):
    """index 页面无用户名 + 看到 takelogin form,cookie 过期。"""


class CloudflareBlockError(PTFansError):
    """收到 Cloudflare challenge HTML 而非业务页面。"""


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _validate_cookie(cookie: str) -> None:
    """简单校验 cookie 字符串是否包含必需的 c_secure_pass。"""
    if not cookie or not cookie.strip():
        raise CookieMissingError(
            "Cookie 字段为空,请按字段说明从浏览器复制 cookie 字符串"
        )
    # 必须有 c_secure_pass(NexusPHP 唯一登录态 cookie)
    if REQUIRED_COOKIE not in cookie:
        raise CookieMissingError(
            f"Cookie 字符串中未找到 `{REQUIRED_COOKIE}=...` 项,"
            "请确保从浏览器 DevTools → Application → Cookies 复制了登录后的 cookie"
        )


def _detect_cloudflare_challenge(html: str, status_code: int) -> None:
    """若响应是 Cloudflare 拦截页面,raise CloudflareBlockError。"""
    if status_code in (403, 503, 429):
        lc = html.lower()
        if "cloudflare" in lc and (
            "challenge" in lc
            or "turnstile" in lc
            or "checking your browser" in lc
            or "just a moment" in lc
        ):
            raise CloudflareBlockError(
                f"Cloudflare 拦截(HTTP {status_code})。可能 IP 触发风控,"
                "建议:换 IP / 等待几小时 / 用与登录浏览器一致的 UA。"
            )


def _parse_user_info(html: str) -> dict[str, Any]:
    """从 index/attendance 页 HTML 提取用户名 + ID + 魔力值。"""
    info: dict[str, Any] = {}
    m = RE_USERNAME.search(html)
    if m:
        info["user_id"] = int(m.group(1))
        info["username"] = m.group(2).strip()
    m = RE_BONUS_VALUE.search(html)
    if m:
        try:
            info["bonus"] = float(m.group(1).replace(",", ""))
        except ValueError:
            info["bonus_raw"] = m.group(1)
    return info


def _check_signed_status(html: str) -> tuple[bool | None, float | None]:
    """判断顶部用户栏是已签 / 未签。

    返回 (signed: True/False/None, today_bonus: float | None)。
    None 表示页面里两种字样都没找到(可能未登录或页面变化)。
    """
    m = RE_SIGNED_TODAY.search(html)
    if m:
        try:
            return True, float(m.group(1))
        except ValueError:
            return True, None
    if RE_NOT_SIGNED.search(html):
        return False, None
    return None, None


def _check_logged_in(html: str) -> bool:
    """页面有 userdetails/logout 链接即视为已登录;若看到 takelogin form 则一定未登录。

    2026-05-18 hotfix:原来用 RE_USERNAME 太严格(要求 class="User_Name"),不同
    主题(BambooGreen 等)class 名不同 → 已登录页面被误判未登录。
    现用 RE_LOGGED_IN_HINT 宽松匹配(userdetails.php?id=<数字> 或 logout 链接)。
    """
    if RE_LOGIN_FORM.search(html):
        return False
    return bool(RE_LOGGED_IN_HINT.search(html))


def _parse_sign_result(html: str) -> dict[str, Any]:
    """从 attendance.php 响应抽取签到结果详情。"""
    out: dict[str, Any] = {}
    m = RE_GAIN_BONUS.search(html)
    if m:
        try:
            out["bonus_gained"] = float(m.group(1))
        except ValueError:
            pass
    m = RE_TOTAL_TIMES.search(html)
    if m:
        out["total_times"] = int(m.group(1))
    m = RE_CONTINUOUS_DAYS.search(html)
    if m:
        out["continuous_days"] = int(m.group(1))
    m = RE_TODAY_RANK.search(html)
    if m:
        out["today_rank"] = int(m.group(1))
    return out


def _signed_already_in_text(html: str) -> bool:
    return any(kw in html for kw in SIGNED_ALREADY_KEYWORDS)


# ---------------------------------------------------------------------------
# HTTP 调用
# ---------------------------------------------------------------------------

def fetch_index(client: httpx.Client, logger: logging.Logger) -> str:
    """GET /index.php,返回 HTML;失败抛 PTFansError。"""
    url = f"{BASE_URL}{INDEX_PATH}"
    logger.debug(f"GET index {url}")
    r = client.get(url)
    _detect_cloudflare_challenge(r.text, r.status_code)
    if r.status_code != 200:
        raise PTFansError(
            f"首页 HTTP {r.status_code}: {r.text[:200]!r}"
        )
    return r.text


def fetch_attendance(client: httpx.Client, logger: logging.Logger) -> str:
    """GET /attendance.php(此请求即触发签到),返回 HTML。"""
    url = f"{BASE_URL}{ATTENDANCE_PATH}"
    logger.debug(f"GET attendance {url}")
    r = client.get(url)
    _detect_cloudflare_challenge(r.text, r.status_code)
    if r.status_code != 200:
        raise PTFansError(
            f"签到接口 HTTP {r.status_code}: {r.text[:200]!r}"
        )
    return r.text


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
            _chunked_sleep(sleep_sec)
        else:
            logger.info("随机延迟掷骰得 0 秒,立即开始签到")
    else:
        logger.info("随机延迟禁用,立即开始签到")

    headers = {
        "User-Agent": ua,
        "Referer": f"{BASE_URL}/",
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,image/apng,*/*;q=0.8"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Upgrade-Insecure-Requests": "1",
        "Cookie": cookie,
    }

    # HTTP 超时:取实例 timeout 与 60 之间的最小值,留 10s 余量
    http_timeout = max(15, min(
        max(15, int(getattr(context, "timeout_sec", 30)) - 10),
        60,
    ))

    try:
        with httpx.Client(
            headers=headers,
            follow_redirects=True,
            timeout=http_timeout,
            http2=False,  # 避免 Cloudflare 偶发 H2 SETTINGS 异常
        ) as client:
            # 3) 拉 index 判断登录态 + 已签状态
            index_html = fetch_index(client, logger)

            if not _check_logged_in(index_html):
                raise NotLoggedInError(
                    "首页未识别到用户名(或检测到 takelogin form),"
                    "cookie 已过期 — 请重新登录 ptfans.cc 复制 c_secure_pass"
                )

            user_info = _parse_user_info(index_html)
            username = user_info.get("username", "<unknown>")
            user_id = user_info.get("user_id")
            bonus_now = user_info.get("bonus")
            logger.info(
                f"已登录: {username}"
                + (f" (id={user_id})" if user_id else "")
                + (f", 当前魔力={bonus_now}" if bonus_now is not None else "")
            )

            signed, today_gain = _check_signed_status(index_html)
            if signed is True and skip_if_signed:
                logger.info(
                    f"首页显示今日已签到(今日得 {today_gain} 魔力值),跳过签到请求"
                )
                return RunResult(
                    success=True,
                    message=(
                        f"今日已签到(首页确认,今日得 {today_gain} 魔力值)"
                        if today_gain is not None
                        else "今日已签到(首页确认)"
                    ),
                    data={
                        "already_signed": True,
                        "user": username,
                        "user_id": user_id,
                        "bonus": bonus_now,
                        "today_gain": today_gain,
                    },
                )
            if signed is None:
                logger.warning(
                    "首页未找到 `[签到已得X]` / `[签到得魔力]` 字样,"
                    "可能站点改版;直接尝试访问 attendance.php"
                )
            else:
                logger.info("首页显示今日未签到,继续访问 attendance.php")

            # 4) 触发签到
            att_html = fetch_attendance(client, logger)
            att_user_info = _parse_user_info(att_html)
            sign_result = _parse_sign_result(att_html)
            logger.debug(f"签到响应解析: {sign_result}")

            # 4a) 主路径:成功 H2
            if RE_SIGN_OK_H2.search(att_html):
                bonus_gained = sign_result.get("bonus_gained")
                cont = sign_result.get("continuous_days")
                total = sign_result.get("total_times")
                rank = sign_result.get("today_rank")
                msg_parts = ["签到成功"]
                if bonus_gained is not None:
                    msg_parts.append(f"获得 {bonus_gained} 魔力值")
                if cont is not None:
                    msg_parts.append(f"连续 {cont} 天")
                if total is not None:
                    msg_parts.append(f"第 {total} 次")
                if rank is not None:
                    msg_parts.append(f"今日排名 {rank}")
                logger.info(" / ".join(msg_parts))
                return RunResult(
                    success=True,
                    message=" / ".join(msg_parts),
                    data={
                        "already_signed": False,
                        "user": att_user_info.get("username", username),
                        "user_id": att_user_info.get("user_id", user_id),
                        "bonus": att_user_info.get("bonus", bonus_now),
                        **sign_result,
                    },
                )

            # 4b) 防御性:NexusPHP 偶尔 attendance.php 走二次访问会回 "您今天已经签到了" 文案
            if _signed_already_in_text(att_html):
                logger.info("attendance.php 返回'今日已签'文案,作为已签到处理")
                return RunResult(
                    success=True,
                    message="今日已签到(attendance.php 文案确认)",
                    data={
                        "already_signed": True,
                        "user": att_user_info.get("username", username),
                        "user_id": att_user_info.get("user_id", user_id),
                        "bonus": att_user_info.get("bonus", bonus_now),
                    },
                )

            # 4c) 防御性:再看 index 顶部是否被 attendance 请求更新(已变成已签状态)
            signed_after, today_gain_after = _check_signed_status(att_html)
            if signed_after is True:
                logger.info(
                    f"attendance.php 顶部已显示 `[签到已得 {today_gain_after}]`,"
                    "判定为签到生效"
                )
                return RunResult(
                    success=True,
                    message=f"签到成功(顶部已得 {today_gain_after} 魔力值)",
                    data={
                        "already_signed": False,
                        "user": att_user_info.get("username", username),
                        "user_id": att_user_info.get("user_id", user_id),
                        "bonus": att_user_info.get("bonus", bonus_now),
                        "today_gain": today_gain_after,
                    },
                )

            # 4d) 失败 H2 或其它情况
            if RE_SIGN_FAIL_H2.search(att_html):
                # 抽 h2 后第一段文字作为 message
                m = re.search(
                    r"<h2[^>]*>签到失败</h2>\s*(?:<[^>]+>\s*)*([^<]{0,300})",
                    att_html,
                    re.IGNORECASE,
                )
                detail = m.group(1).strip() if m else "(无详情)"
                return RunResult(
                    success=False,
                    message=f"签到失败: {detail}",
                    data={"html_excerpt": att_html[:500]},
                )

            # 4e) 兜底:HTML 解析不出任何已知 marker
            return RunResult(
                success=False,
                message=(
                    "签到接口响应未识别(无成功/失败 H2,无已签到字样)。"
                    "可能页面改版或被风控,请人工访问 attendance.php 确认。"
                ),
                data={"html_excerpt": att_html[:500]},
            )

    except PTFansError as e:
        logger.error(f"业务错误: {e}")
        return RunResult(success=False, message=str(e))
    except httpx.HTTPError as e:
        logger.error(f"网络错误: {type(e).__name__}: {e}")
        return RunResult(
            success=False,
            message=f"网络错误({type(e).__name__}): {e}",
        )
    # 其余未捕获异常让 sandbox runner 转成 status=error(traceback 进 stderr)


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
        $env:PTFANS_COOKIE="c_secure_pass=eyJ1c..."
        python main.py

        # 或者直接给完整 JSON config:
        $env:PTFANS_CONFIG='{"cookie":"...","random_delay_sec":0,"skip_if_signed":true}'
        python main.py
    """
    logging.basicConfig(
        level=logging.DEBUG if os.environ.get("PTFANS_DEBUG") else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    @dataclass
    class _LocalContext:
        run_id: int = 0
        instance_id: int = 0
        instance_name: str = "local-test"
        script_slug: str = "ptfans"
        script_dir: str = os.path.dirname(os.path.abspath(__file__))
        data_dir: str = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "_local_data"
        )
        timeout_sec: int = 60
        trigger_type: str = "manual"
        attempt: int = 1
        logger: logging.Logger = field(default_factory=lambda: logging.getLogger("ptfans"))

        def notify(self, title: str, body: str = "", level: str = "info") -> None:
            self.logger.info(f"[notify {level}] {title}: {body}")

    # 加载 config:优先 PTFANS_CONFIG(JSON),否则用零散环境变量拼一个
    raw_cfg = os.environ.get("PTFANS_CONFIG")
    if raw_cfg:
        try:
            cfg = json.loads(raw_cfg)
        except json.JSONDecodeError as e:
            print(f"PTFANS_CONFIG 不是合法 JSON: {e}", file=sys.stderr)
            sys.exit(2)
    else:
        cfg = {
            "cookie": os.environ.get("PTFANS_COOKIE", ""),
            "random_delay_sec": int(os.environ.get("PTFANS_DELAY", "0") or 0),
            "skip_if_signed": os.environ.get("PTFANS_SKIP_IF_SIGNED", "1")
                not in ("0", "false", "False"),
        }
        if os.environ.get("PTFANS_UA"):
            cfg["user_agent"] = os.environ["PTFANS_UA"]

    ctx = _LocalContext()
    os.makedirs(ctx.data_dir, exist_ok=True)

    print("=" * 60, file=sys.stderr)
    print(f"PTFans 签到 · 本地测试 · script_dir={ctx.script_dir}", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    result = run(cfg, ctx)
    out = json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
    print(out)
    sys.exit(0 if result.success else 1)
