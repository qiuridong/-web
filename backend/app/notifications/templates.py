"""通知模板渲染 — jinja2 + 自定义 filter + 默认模板。

实现见 `进度/设计/后端架构.md` § 9.4。

公开
----
- ``DEFAULT_TITLE_TEMPLATE`` / ``DEFAULT_BODY_TEMPLATE``  设计稿 § 9.4 默认值
- ``render_notification(template_str_or_none, ctx) -> (title, body)``
- ``build_context(*, run, instance, script, event)``       把 ORM 拼成模板可用 dict
- ``build_sample_context(event='failure')``                rule preview 用假数据

模板上下文(供 jinja2):
- ``event``     str   ("success"/"failure"/"error"/"timeout")
- ``script``    dict  (slug, name, version, description, ...)
- ``instance``  dict  (id, name, cron_expr, timeout_sec, ...)
- ``run``       dict  (id, status, exit_code, started_at, finished_at,
                       duration_ms, result_message, stdout, stderr,
                       trigger_type, host, ...)

自定义 filter:
- ``tail(n)``           取尾部 N 行
- ``human_duration``    ms → "1m 23s"
- ``local_time(tz)``    datetime → 指定时区字符串
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from jinja2 import Environment, StrictUndefined, select_autoescape


# ============================================================
# 默认模板(设计稿 § 9.4)
# ============================================================
DEFAULT_TITLE_TEMPLATE = (
    "[{{ event | upper }}] {{ instance.name }} - {{ script.name }}"
)

DEFAULT_BODY_TEMPLATE = """脚本: {{ script.name }} ({{ script.slug }})
实例: {{ instance.name }}
状态: {{ run.status }}
开始: {{ run.started_at }}
耗时: {{ run.duration_ms }} ms
{% if run.result_message %}
结果: {{ run.result_message }}
{% endif %}
{% if event in ['failure', 'error', 'timeout'] and run.stderr %}
--- stderr (尾部) ---
{{ run.stderr | tail(20) }}
{% endif %}"""


# ============================================================
# 自定义 filter
# ============================================================
def filter_tail(text: Any, n: int = 20) -> str:
    """取字符串尾部 n 行;非字符串自动 str()。"""
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    lines = text.splitlines()
    if n is None or n <= 0:
        return ""
    if len(lines) <= n:
        return text
    return "\n".join(lines[-n:])


def filter_human_duration(ms: Any) -> str:
    """毫秒 → ``"1m 23s"`` / ``"500ms"`` / ``"3h 4m"``。

    None / 非数字 → ``"-"``。
    """
    if ms is None:
        return "-"
    try:
        total_ms = int(ms)
    except (TypeError, ValueError):
        return "-"
    if total_ms < 1000:
        return f"{total_ms}ms"
    total_seconds = total_ms // 1000
    hours, rem = divmod(total_seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    parts: list[str] = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds or not parts:
        parts.append(f"{seconds}s")
    return " ".join(parts)


def filter_local_time(
    value: Any, tz: str = "Asia/Shanghai", fmt: str | None = None
) -> str:
    """把 datetime / ISO 字符串转换到指定时区。

    fmt 不指定时默认 ``"%Y-%m-%d %H:%M:%S"``;tz 非法静默退回 UTC。
    """
    if value is None:
        return ""
    fmt = fmt or "%Y-%m-%d %H:%M:%S"
    try:
        zone: timezone | ZoneInfo = ZoneInfo(tz)
    except Exception:  # noqa: BLE001
        zone = timezone.utc

    dt: datetime | None = None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    if dt is None:
        return str(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(zone).strftime(fmt)


# ============================================================
# Environment 单例
# ============================================================
def _make_env() -> Environment:
    """构建 jinja2 Environment。

    设计:
    - ``StrictUndefined``:模板写错变量名直接报错(便于 preview/调试)
    - autoescape 默认关(text 类通知,转义会破坏样式)
    - trim_blocks + lstrip_blocks:控制块不留下额外空行
    """
    env = Environment(
        autoescape=select_autoescape(default_for_string=False, default=False),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=False,
        undefined=StrictUndefined,
        enable_async=False,
    )
    env.filters["tail"] = filter_tail
    env.filters["human_duration"] = filter_human_duration
    env.filters["local_time"] = filter_local_time
    return env


_env: Environment = _make_env()


def get_env() -> Environment:
    """获取共享 Environment(单例)。"""
    return _env


# ============================================================
# 渲染入口
# ============================================================
def render_notification(
    template_str: str | None,
    ctx: dict[str, Any],
) -> tuple[str, str]:
    """渲染通知 title + body。

    模板格式约定
    ------------
    - **None / 空白**:用 ``DEFAULT_TITLE_TEMPLATE`` + ``DEFAULT_BODY_TEMPLATE``
    - **包含一行 `---` 分隔符**:上半段是 title 模板,下半段是 body 模板
    - **其它**:整段当作 body 模板,title 走默认

    返回 ``(title, body)``,均为渲染后的纯字符串。
    """
    title_tpl: str
    body_tpl: str
    if not template_str or not template_str.strip():
        title_tpl, body_tpl = DEFAULT_TITLE_TEMPLATE, DEFAULT_BODY_TEMPLATE
    else:
        title_part, body_part = _split_template(template_str)
        if title_part is not None:
            title_tpl = title_part.strip() or DEFAULT_TITLE_TEMPLATE
            body_tpl = body_part.strip() or DEFAULT_BODY_TEMPLATE
        else:
            title_tpl = DEFAULT_TITLE_TEMPLATE
            body_tpl = template_str

    title = _render_one(title_tpl, ctx)
    body = _render_one(body_tpl, ctx)
    return title, body


def _split_template(text: str) -> tuple[str | None, str]:
    """以一行 ``---`` 切分模板。

    返回 ``(title_part, body_part)``;若无分隔符返回 ``(None, "")``。
    """
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if line.strip() == "---":
            title_part = "\n".join(lines[:idx])
            body_part = "\n".join(lines[idx + 1 :])
            return title_part, body_part
    return None, ""


def _render_one(template_str: str, ctx: dict[str, Any]) -> str:
    """单段 jinja2 渲染。"""
    template = _env.from_string(template_str)
    rendered = template.render(**ctx)
    return rendered.strip()


# ============================================================
# 上下文构造
# ============================================================
def build_context(
    *,
    run: Any,
    instance: Any,
    script: Any,
    event: str,
) -> dict[str, Any]:
    """从 ORM 对象生成模板上下文 dict。

    传 None 时该段返回占位空 dict(避免模板访问异常)。
    """
    return {
        "event": event,
        "script": _dump_script(script),
        "instance": _dump_instance(instance),
        "run": _dump_run(run),
    }


def _dump_script(script: Any) -> dict[str, Any]:
    if script is None:
        return {"slug": "", "name": "", "version": "", "description": ""}
    return {
        "id": getattr(script, "id", None),
        "slug": getattr(script, "slug", "") or "",
        "name": getattr(script, "name", "") or "",
        "description": getattr(script, "description", "") or "",
        "version": getattr(script, "version", "") or "",
        "author": getattr(script, "author", None),
        "homepage": getattr(script, "homepage", None),
    }


def _dump_instance(instance: Any) -> dict[str, Any]:
    if instance is None:
        return {"id": 0, "name": "", "cron_expr": "", "timeout_sec": 0}
    return {
        "id": getattr(instance, "id", 0) or 0,
        "name": getattr(instance, "name", "") or "",
        "description": getattr(instance, "description", None),
        "cron_expr": getattr(instance, "cron_expr", None),
        "timeout_sec": getattr(instance, "timeout_sec", None),
        "enabled": bool(getattr(instance, "enabled", True)),
    }


def _dump_run(run: Any) -> dict[str, Any]:
    if run is None:
        return {
            "id": 0,
            "status": "",
            "exit_code": None,
            "started_at": "",
            "finished_at": "",
            "duration_ms": 0,
            "result_message": "",
            "stdout": "",
            "stderr": "",
            "trigger_type": "",
        }
    return {
        "id": getattr(run, "id", 0) or 0,
        "status": getattr(run, "status", "") or "",
        "exit_code": getattr(run, "exit_code", None),
        "started_at": _iso(getattr(run, "started_at", None)),
        "finished_at": _iso(getattr(run, "finished_at", None)),
        "duration_ms": getattr(run, "duration_ms", None),
        "result_message": getattr(run, "result_message", "") or "",
        "stdout": getattr(run, "stdout", "") or "",
        "stderr": getattr(run, "stderr", "") or "",
        "trigger_type": getattr(run, "trigger_type", "") or "",
        "host": getattr(run, "host", None),
    }


def _iso(dt: datetime | None) -> str:
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


# ============================================================
# Preview — 假数据 ctx
# ============================================================
def build_sample_context(event: str = "failure") -> dict[str, Any]:
    """构造假数据 ctx,供 rule preview / 单元测试用。"""
    now = datetime.now(timezone.utc)
    is_failure = event in ("failure", "error", "timeout")
    return {
        "event": event,
        "script": {
            "id": 1,
            "slug": "demo-script",
            "name": "Demo 签到",
            "description": "示例脚本",
            "version": "1.0.0",
            "author": "system",
            "homepage": None,
        },
        "instance": {
            "id": 1,
            "name": "我的账号",
            "description": "示例实例",
            "cron_expr": "0 9 * * *",
            "timeout_sec": 300,
            "enabled": True,
        },
        "run": {
            "id": 100,
            "status": "failure" if is_failure else "success",
            "exit_code": 1 if is_failure else 0,
            "started_at": now.isoformat(),
            "finished_at": now.isoformat(),
            "duration_ms": 1234,
            "result_message": (
                "示例失败原因" if is_failure else "签到成功,获得 10 积分"
            ),
            "stdout": "示例 stdout 行 1\n示例 stdout 行 2",
            "stderr": (
                "示例 stderr 行 1\nTraceback (most recent call last):\n  File ..."
                if is_failure
                else ""
            ),
            "trigger_type": "scheduled",
            "host": "localhost",
        },
    }
