"""独立子进程脚本执行入口 — 由 executor 用 ``python -u sandbox_runner.py`` 启动。

**audit Critical #1 隔离方案**
-----------------------------
这个文件**有意不在 ``app/`` 树下**,启动时不需要 PYTHONPATH 指向 backend/,
脚本子进程因此**无法 ``import app.core.crypto`` 或任何 ``app.*`` 模块**,
即便脚本作者尝试也会拿 ``ModuleNotFoundError``。

历史上(MVP-2/3)用 ``python -u -m app.runner.sandbox`` 启动,
executor 透传 ``PYTHONPATH=backend/``,导致脚本可读 Fernet 主密钥(等价于密钥泄露)。

设计稿契约见 `进度/设计/后端架构.md` § 3.4 + § 3.4.2 + § 3.3 + § 5.5。

stdio 协议
----------
**输入(stdin 单行 JSON)**:

    {"config": {...}, "context": {"run_id":1,"instance_id":1,"script_dir":"...",...}}

**输出(stdout)**:

    [脚本 print 的普通行]
    [脚本 print 的普通行]
    ...
    __RUN_RESULT__{"success":true,"message":"...","data":{...}}

约定
----
- exit code:成功 → 0,失败 → 1(主程序据此判 ``status=error``)
- stdout 普通输出 → 主程序广播给 SSE + 落库
- 子进程的 logger 名 = ``script.<slug>``,日志格式简洁

依赖
----
**只使用 Python 标准库**,不 import ``app.*``、不 import 第三方包(脚本可 import
自己 venv 中的包)。``__RUN_RESULT__`` 协议常量与 JSON 序列化均 inline 在此文件内。
"""
from __future__ import annotations

import importlib.util
import json
import logging
import os
import sys
import traceback
from pathlib import Path
from types import SimpleNamespace
from typing import Any


# ============================================================
# stdio 协议常量(从 app.runner.stdio_protocol inline 过来,
# 防止依赖 app/ 树)
# ============================================================
RESULT_MARKER: str = "__RUN_RESULT__"
RESULT_DATA_MAX: int = 16384  # 16 KiB,与 executor 一致


def format_result(
    *,
    success: bool,
    message: str = "",
    data: dict[str, Any] | None = None,
) -> str:
    """RunResult dict → 协议行(不含末尾 \\n)。"""
    payload = {
        "success": bool(success),
        "message": str(message or "")[:512],
        "data": data or {},
    }
    return RESULT_MARKER + json.dumps(
        payload, ensure_ascii=False, separators=(",", ":")
    )


def unpack_input(line: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """stdin 第一行 → (config, context)。

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


# ============================================================
# 隔离 — 启动一开始就把 sys.path 缩成"只剩 stdlib + 脚本目录将后加"
# ============================================================
def _isolate_sys_path() -> None:
    """从 sys.path 移除可让脚本 ``import app.*`` 的路径。

    audit Critical #1 — 防止脚本 import ``app.core.crypto`` 等敏感模块拿密钥。

    策略
    ----
    1. **移除 backend/ 目录本身**(即 ``Path(__file__).parent``)— 防止脚本
       直接 ``import app`` (因为 backend/app/__init__.py 让 backend/ 可导出
       ``app`` 包)
    2. **移除任何以 backend/ 为前缀且确实含 ``app/__init__.py`` 的路径**
       (兜底,防 PYTHONPATH 透传)
    3. **保留 venv 的 site-packages**(典型路径如
       ``backend/.venv/Lib/site-packages``)— 脚本需要从 venv 中 import httpx 等
    4. **保留 Python stdlib / DLLs / Lib**

    实现:对每个路径,只在以下两种情况下删除:
       (a) 它正好等于 backend/
       (b) 它就是 backend/ 直接子目录 ``app/`` 的容器(已在 (a) 中处理)
       注:venv 的 site-packages 在 ``backend/.venv/Lib/site-packages``,
           不等于 backend/,**不会被误删**

    并主动 ``del sys.modules['app']``(若已加载)— 加层保险。
    """
    backend_dir = str(Path(__file__).resolve().parent)
    new_path: list[str] = []
    for p in sys.path:
        if not p:
            new_path.append(p)
            continue
        try:
            abs_p = str(Path(p).resolve())
        except (OSError, ValueError):
            new_path.append(p)
            continue
        # 严格隔离:移除 backend 目录本身(这是 'app' 包所在父目录)
        if abs_p == backend_dir:
            continue
        new_path.append(p)
    sys.path[:] = new_path

    # 主动卸载 app 包(若已加载)
    for mod_name in list(sys.modules.keys()):
        if mod_name == "app" or mod_name.startswith("app."):
            del sys.modules[mod_name]


# ============================================================
# Logger / notify / context 构造
# ============================================================
def _build_logger(slug: str) -> logging.Logger:
    """子进程内的 logger — 简洁格式,直输 stderr。"""
    logger = logging.getLogger(f"script.{slug}")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    h = logging.StreamHandler(stream=sys.stderr)
    h.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(h)
    logger.propagate = False
    return logger


def _make_notify(slug: str, logger: logging.Logger):
    """RunContext.notify — v1 仅写日志(后续可改成向主程序推一条 sideband 通知)。"""

    def notify(title: str, body: str = "", level: str = "info") -> None:
        logger.info(f"[notify {level}] {title}: {body}")

    return notify


def _load_main_module(script_dir: Path) -> Any:
    """从 ``script_dir/main.py`` 加载并返回 module。"""
    main_path = script_dir / "main.py"
    if not main_path.is_file():
        raise FileNotFoundError(f"脚本 main.py 不存在: {main_path}")

    # 把脚本目录加进 sys.path 让 main.py 能 `import helpers.x`
    script_dir_str = str(script_dir)
    if script_dir_str not in sys.path:
        sys.path.insert(0, script_dir_str)

    # 用唯一 module 名避免 sys.modules 冲突
    module_name = "_sandbox_script_main"
    spec = importlib.util.spec_from_file_location(module_name, main_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法构造 spec: {main_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _build_context(
    raw: dict[str, Any], logger: logging.Logger, slug: str
) -> SimpleNamespace:
    """组装 RunContext,符合 § 3.3.1 字段约定。"""
    ctx = SimpleNamespace(
        run_id=int(raw.get("run_id") or 0),
        instance_id=int(raw.get("instance_id") or 0),
        instance_name=str(raw.get("instance_name") or ""),
        script_slug=str(raw.get("script_slug") or slug),
        script_dir=str(raw.get("script_dir") or ""),
        data_dir=str(raw.get("data_dir") or ""),
        timeout_sec=int(raw.get("timeout_sec") or 300),
        trigger_type=str(raw.get("trigger_type") or "manual"),
        attempt=int(raw.get("attempt") or 1),
        logger=logger,
        notify=_make_notify(slug, logger),
    )
    if ctx.data_dir:
        try:
            Path(ctx.data_dir).mkdir(parents=True, exist_ok=True)
        except OSError as exc:  # pragma: no cover
            logger.warning(f"data_dir 创建失败 {ctx.data_dir}: {exc}")
    return ctx


def _result_to_dict(result: Any) -> dict[str, Any]:
    """容忍多种 RunResult 形状(dict / dataclass with to_dict / setattr 对象)。"""
    if isinstance(result, dict):
        return {
            "success": bool(result.get("success", False)),
            "message": str(result.get("message", "") or ""),
            "data": result.get("data") or {},
        }
    if hasattr(result, "to_dict") and callable(result.to_dict):
        d = result.to_dict()
        if isinstance(d, dict):
            return _result_to_dict(d)
    if hasattr(result, "success"):
        return {
            "success": bool(getattr(result, "success", False)),
            "message": str(getattr(result, "message", "") or ""),
            "data": getattr(result, "data", None) or {},
        }
    return {
        "success": False,
        "message": (
            f"脚本 run() 返回值无法识别:type={type(result).__name__}, "
            f"repr={result!r}"[:480]
        ),
        "data": {},
    }


def _emit_result(payload: dict[str, Any]) -> None:
    """把 RunResult 写到 stdout 最后一行。"""
    line = format_result(
        success=bool(payload.get("success", False)),
        message=str(payload.get("message", "")),
        data=payload.get("data") or {},
    )
    print("", flush=True)
    print(line, flush=True)


def main() -> int:
    """sandbox 入口。返回 exit code,0=成功,1=失败/异常。"""
    # ===== 0. 立即隔离 sys.path,卸载 app =====
    _isolate_sys_path()

    slug_fallback = os.environ.get("SCRIPT_SLUG", "unknown")

    # ===== 1. 读 stdin =====
    raw_line = sys.stdin.readline()
    if not raw_line:
        logger = _build_logger(slug_fallback)
        logger.error("sandbox 未从 stdin 收到任何输入")
        _emit_result(
            {
                "success": False,
                "message": "sandbox 未从 stdin 收到任何输入",
                "data": {},
            }
        )
        return 1

    try:
        config, ctx_raw = unpack_input(raw_line)
    except (ValueError, json.JSONDecodeError) as exc:
        logger = _build_logger(slug_fallback)
        logger.error(f"stdin JSON 解析失败: {exc}")
        traceback.print_exc(file=sys.stderr)
        _emit_result(
            {
                "success": False,
                "message": f"sandbox stdin 解析失败: {exc}",
                "data": {},
            }
        )
        return 1

    slug = str(ctx_raw.get("script_slug") or slug_fallback)
    logger = _build_logger(slug)

    # ===== 平台级 UX:用户立即运行(manual)→ 强制跳过所有脚本的 random_delay_sec =====
    # "立即"就该立即,不被脚本作者的延迟设计影响。
    # 这是平台契约层的统一行为(所有脚本受益),避免每个脚本作者都要自己处理 trigger_type。
    # cron / scheduler 触发(trigger_type != 'manual')仍走脚本配置的 random_delay_sec
    # (scheduled 错峰避风控合理)。
    trigger_type = str(ctx_raw.get("trigger_type") or "")
    if trigger_type == "manual" and isinstance(config, dict) and "random_delay_sec" in config:
        original_delay = config.get("random_delay_sec")
        if original_delay and int(original_delay or 0) > 0:
            config = {**config, "random_delay_sec": 0}
            logger.info(
                f"平台 UX:trigger_type=manual,强制 random_delay_sec=0 "
                f"(原配置 {original_delay}s,立即运行不等延迟)"
            )

    # ===== 2. 切 cwd 到 script_dir 并加载 main =====
    script_dir_str = str(ctx_raw.get("script_dir") or "")
    if not script_dir_str:
        msg = "context.script_dir 为空,无法定位脚本"
        logger.error(msg)
        _emit_result({"success": False, "message": msg, "data": {}})
        return 1

    script_dir = Path(script_dir_str).resolve()
    if not script_dir.is_dir():
        msg = f"script_dir 不存在或不是目录: {script_dir}"
        logger.error(msg)
        _emit_result({"success": False, "message": msg, "data": {}})
        return 1

    try:
        os.chdir(script_dir)
    except OSError as exc:
        msg = f"切换工作目录失败 {script_dir}: {exc}"
        logger.error(msg)
        _emit_result({"success": False, "message": msg, "data": {}})
        return 1

    try:
        module = _load_main_module(script_dir)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"加载脚本失败: {type(exc).__name__}: {exc}")
        traceback.print_exc(file=sys.stderr)
        _emit_result(
            {
                "success": False,
                "message": f"脚本加载失败 {type(exc).__name__}: {exc}",
                "data": {},
            }
        )
        return 1

    run_func = getattr(module, "run", None)
    if not callable(run_func):
        msg = "脚本 main 模块未定义可调用的 run(config, context) 函数"
        logger.error(msg)
        _emit_result({"success": False, "message": msg, "data": {}})
        return 1

    # ===== 3. 构造 context + 执行 =====
    context = _build_context(ctx_raw, logger, slug)
    logger.info(
        f"sandbox 启动 slug={slug} instance_id={context.instance_id} "
        f"run_id={context.run_id} timeout={context.timeout_sec}s"
    )

    try:
        result = run_func(config, context)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
        msg = f"脚本调用 SystemExit({exc.code})"
        logger.error(msg)
        _emit_result(
            {"success": code == 0, "message": msg, "data": {}}
        )
        return 0 if code == 0 else 1
    except KeyboardInterrupt:
        msg = "脚本被 KeyboardInterrupt 中断"
        logger.warning(msg)
        _emit_result({"success": False, "message": msg, "data": {}})
        return 1
    except Exception as exc:  # noqa: BLE001
        logger.error(f"脚本运行异常: {type(exc).__name__}: {exc}")
        traceback.print_exc(file=sys.stderr)
        _emit_result(
            {
                "success": False,
                "message": f"{type(exc).__name__}: {exc}",
                "data": {},
            }
        )
        return 1

    # ===== 4. 写 RunResult =====
    payload = _result_to_dict(result)
    _emit_result(payload)
    logger.info(
        f"sandbox 结束 success={payload['success']} msg={payload['message']!r}"
    )
    return 0 if payload["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
