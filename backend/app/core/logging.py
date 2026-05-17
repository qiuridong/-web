"""loguru 日志配置 + stdlib logging 拦截。

详见 `进度/设计/后端架构.md` § 8.3 / § 8.4。

输出目标:
- `sys.stderr`:供 docker logs 收集(LEVEL=INFO 起,彩色)
- `<logs_dir>/app.log`:全量(LEVEL=DEBUG,20MB rotation,30 天保留,zip 压缩)
- `<logs_dir>/error.log`:仅 ERROR 及以上,便于排查

stdlib logging(uvicorn / sqlalchemy / apscheduler / apprise 等)通过 `InterceptHandler`
转发到 loguru,确保单一日志通道。
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from types import FrameType
from typing import Any

from loguru import logger


class InterceptHandler(logging.Handler):
    """把 stdlib logging 调用转发到 loguru。

    取自 loguru 官方推荐做法。挂在 root logger 上即可拦截所有 stdlib 日志。
    """

    def emit(self, record: logging.LogRecord) -> None:
        # 把 stdlib level 名转 loguru
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # 找到调用者的真实 frame(跳过 logging 内部栈帧)
        frame: FrameType | None = logging.currentframe()
        depth = 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


_DEFAULT_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{extra[trace_id]}</cyan> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)


_FILE_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
    "{level: <8} | "
    "{extra[trace_id]} | "
    "{name}:{function}:{line} | "
    "{message}"
)


def configure_logging(
    level: str = "INFO",
    *,
    logs_dir: Path | None = None,
) -> None:
    """配置 loguru sinks 并接管 stdlib logging。

    幂等:重复调用会先 remove() 默认 sink。
    """
    # 清空 loguru 默认 stderr handler
    logger.remove()

    # extra={"trace_id": "-"} 作为缺省值,中间件后续 bind() 会覆盖
    logger.configure(extra={"trace_id": "-"})

    # ===== stderr sink(docker logs / journalctl 收集)=====
    logger.add(
        sys.stderr,
        level=level.upper(),
        format=_DEFAULT_FORMAT,
        colorize=True,
        backtrace=False,  # 生产不暴露 traceback;ERROR 级别走文件
        diagnose=False,
    )

    # ===== 文件 sink(若有 logs 目录)=====
    if logs_dir is not None:
        logs_dir.mkdir(parents=True, exist_ok=True)

        logger.add(
            logs_dir / "app.log",
            level="DEBUG",
            format=_FILE_FORMAT,
            rotation="20 MB",
            retention="30 days",
            compression="zip",
            encoding="utf-8",
            enqueue=True,  # 多线程/多进程安全
        )
        logger.add(
            logs_dir / "error.log",
            level="ERROR",
            format=_FILE_FORMAT,
            rotation="20 MB",
            retention="60 days",
            compression="zip",
            encoding="utf-8",
            backtrace=True,
            diagnose=True,
            enqueue=True,
        )

    # ===== 接管 stdlib logging =====
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    # 让 uvicorn / sqlalchemy / apscheduler 走我们的 sink
    for noisy in (
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
        "fastapi",
        "sqlalchemy.engine",
        "apscheduler",
        "apprise",
    ):
        std_logger = logging.getLogger(noisy)
        std_logger.handlers = [InterceptHandler()]
        std_logger.propagate = False


def get_logger(**bind_extra: Any) -> Any:
    """获取一个绑定上下文的 logger 实例。

    示例::

        log = get_logger(run_id=123)
        log.info("启动子进程")
    """
    return logger.bind(**bind_extra)
