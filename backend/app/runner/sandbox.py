"""子进程脚本执行入口 — 被 ``python -m app.runner.sandbox`` 启动。

实现见 `进度/设计/后端架构.md` § 3.4 + § 3.4.2 + § 3.3。

流程
----
1. 从 stdin 读取一行 JSON(config + context)
2. 把 ``scripts/<slug>/`` 加进 ``sys.path``,动态 import ``main`` 模块
3. 构造 RunContext(SimpleNamespace + logger + 简单 notify)
4. 调用 ``run(config, context)``,正常 → 解析 RunResult
5. 把 RunResult 以 ``__RUN_RESULT__`` 前缀写到 stdout 最后一行
6. 任意未捕获异常 → stderr 写 traceback + stdout 写
   ``__RUN_RESULT__{"success":false,...}``,exit 1

约定
----
- exit code: 成功 → 0,失败 → 1(主程序据此判 ``status=error``)
- stdout 普通输出 → 主程序广播给 SSE + 落库
- 子进程的 logger 名 = ``script.<slug>``,日志格式简洁
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import logging
import os
import sys
import traceback
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from app.runner.stdio_protocol import (
    RESULT_MARKER,
    format_result,
    unpack_input,
)


def _build_logger(slug: str) -> logging.Logger:
    """子进程内的 logger — 简洁格式,直输 stderr。

    stdout 留给"普通业务输出";logger 走 stderr 让主程序区分日志与结果行
    更轻松(虽然 stdout 也行,但 stderr 让 ``__RUN_RESULT__`` 行不会被
    logger 行夹杂)。
    """
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
    """RunContext.notify — v1 仅写日志,后续可改为向主程序推一条 sideband 通知。"""

    def notify(title: str, body: str = "", level: str = "info") -> None:
        logger.info(f"[notify {level}] {title}: {body}")

    return notify


def _load_main_module(script_dir: Path) -> Any:
    """从 ``script_dir/main.py`` 加载并返回 module 对象。

    用 ``importlib.util.spec_from_file_location`` 而非 ``importlib.import_module``,
    因为脚本目录通常不在 ``sys.path`` 里,而且我们希望 module 名稳定
    (``script.main``)避免与主程序模块冲突。
    """
    main_path = script_dir / "main.py"
    if not main_path.is_file():
        raise FileNotFoundError(
            f"脚本 main.py 不存在: {main_path}"
        )

    # 把脚本目录加进 sys.path 让 main.py 能 `import helpers.x`
    script_dir_str = str(script_dir)
    if script_dir_str not in sys.path:
        sys.path.insert(0, script_dir_str)

    # 用唯一 module 名避免 sys.modules 冲突(同进程不会跑多个脚本,但保险)
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
    """把从 stdin 收到的 context dict + logger / notify 组装成 RunContext。

    符合 § 3.3.1 的字段约定。
    """
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
    # 确保 data_dir 存在(主程序也建过,这里防御性 mkdir)
    if ctx.data_dir:
        try:
            Path(ctx.data_dir).mkdir(parents=True, exist_ok=True)
        except OSError as exc:  # pragma: no cover
            logger.warning(f"data_dir 创建失败 {ctx.data_dir}: {exc}")
    return ctx


def _result_to_dict(result: Any) -> dict[str, Any]:
    """容忍多种 RunResult 形状:

    - 已经是 dict
    - 带 ``to_dict()`` 方法(coklw 风格的 dataclass)
    - 任意带 ``success`` / ``message`` / ``data`` 属性的对象(setattr 风格)
    """
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
    # 兜底:整个对象 repr 进 message
    return {
        "success": False,
        "message": (
            f"脚本 run() 返回值无法识别:type={type(result).__name__}, "
            f"repr={result!r}"[:480]
        ),
        "data": {},
    }


def _emit_result(payload: dict[str, Any]) -> None:
    """把 RunResult 写到 stdout 最后一行(单独换行使前面输出可读)。"""
    line = format_result(
        success=bool(payload.get("success", False)),
        message=str(payload.get("message", "")),
        data=payload.get("data") or {},
    )
    # 先打一个空行,让结果行从新行开始 —— 防止脚本最后一行没换行污染解析
    print("", flush=True)
    print(line, flush=True)


def main() -> int:
    """sandbox 入口。返回 exit code,0=成功,1=失败/异常。"""
    # 设默认 logger;脚本未提供 slug 时 fallback
    slug_fallback = os.environ.get("SCRIPT_SLUG", "unknown")

    # ===== 1. 读 stdin =====
    raw_line = sys.stdin.readline()
    if not raw_line:
        # 没有输入 —— 直接报错
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
    except Exception as exc:  # noqa: BLE001 — 任何 import 失败都包成 RunResult
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
    except SystemExit as exc:  # 脚本主动 exit
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
    except Exception as exc:  # noqa: BLE001 — 兜底成 error
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
