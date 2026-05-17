"""主程序 ⇄ sandbox 子进程的 stdio JSON 协议。

实现见 `进度/设计/后端架构.md` § 3.4.2。

通信流向
--------
主程序 → 子进程(stdin 单条 JSON,以 ``\\n`` 结束)::

    {"config": {...}, "context": {...}}

子进程 → 主程序(stdout):
- 普通行:脚本 ``print`` / logger 输出
- 最后一行:``__RUN_RESULT__{"success":...,"message":"...","data":{...}}``

公开接口
--------
- :data:`RESULT_MARKER`            常量 ``__RUN_RESULT__``
- :class:`RunContextPayload`       传给子进程的 context 字段
- :class:`SandboxInput`            stdin 的完整 JSON
- :func:`pack_input(...)`          打包 SandboxInput 为可写到 stdin 的字符串
- :func:`parse_result_line(line)`  解析 ``__RUN_RESULT__`` 行 → dict | None
- :func:`format_result(...)`       把 RunResult dict 序列化为协议行
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

#: 子进程把最终结果以这个前缀打到 stdout 最后一行
RESULT_MARKER: str = "__RUN_RESULT__"


@dataclass
class RunContextPayload:
    """传给子进程的 context 字段 — 简化版,只放可序列化的纯数据。

    sandbox 启动后会把这些字段 + ``logger`` / ``notify`` 包成 SimpleNamespace
    传给脚本的 ``run(config, context)``,符合 § 3.3.1 RunContext 契约。
    """

    run_id: int
    instance_id: int
    instance_name: str
    script_slug: str
    script_dir: str
    data_dir: str
    timeout_sec: int
    trigger_type: str
    attempt: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SandboxInput:
    """打包到 stdin 的 JSON。"""

    config: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)

    def to_json_line(self) -> str:
        """序列化为一行,末尾带 ``\\n``。"""
        return (
            json.dumps(
                {"config": self.config, "context": self.context},
                ensure_ascii=False,
                separators=(",", ":"),
            )
            + "\n"
        )


# ============================================================
# 主程序侧:打包 / 解析
# ============================================================
def pack_input(
    *,
    config: dict[str, Any],
    context: RunContextPayload,
) -> str:
    """主程序用:把 config + context 打包成 stdin 单行 JSON。"""
    payload = SandboxInput(config=config, context=context.to_dict())
    return payload.to_json_line()


def parse_result_line(line: str) -> dict[str, Any] | None:
    """从一行文本里解析 ``__RUN_RESULT__`` payload。

    :returns: 解析成功 → dict;不是结果行或解析失败 → None

    设计稿 § 3.4.2:子进程把 RunResult 序列化为 JSON,以
    ``__RUN_RESULT__`` 前缀作为 stdout 最后一行。本函数容忍前后空白与 BOM。
    """
    if not line:
        return None
    s = line.lstrip("﻿").rstrip()  # 去 BOM + 行尾空白
    if not s.startswith(RESULT_MARKER):
        return None
    payload = s[len(RESULT_MARKER):]
    try:
        data = json.loads(payload)
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def format_result(
    *,
    success: bool,
    message: str = "",
    data: dict[str, Any] | None = None,
) -> str:
    """子进程用:把 RunResult 序列化为协议行(不含末尾 ``\\n``)。"""
    payload = {
        "success": bool(success),
        "message": str(message or "")[:512],
        "data": data or {},
    }
    return RESULT_MARKER + json.dumps(
        payload, ensure_ascii=False, separators=(",", ":")
    )


# ============================================================
# 子进程侧:从 stdin 解析
# ============================================================
def unpack_input(line: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """子进程用:解析 stdin 第一行 → ``(config, context)``。

    :raises ValueError: 非合法 JSON 或缺字段
    """
    if not line:
        raise ValueError("stdin 输入为空")
    data = json.loads(line)
    if not isinstance(data, dict):
        raise ValueError(f"stdin 顶层必须是 dict,实际 {type(data).__name__}")
    config = data.get("config") or {}
    context = data.get("context") or {}
    if not isinstance(config, dict):
        raise ValueError(f"config 必须是 dict,实际 {type(config).__name__}")
    if not isinstance(context, dict):
        raise ValueError(f"context 必须是 dict,实际 {type(context).__name__}")
    return config, context
