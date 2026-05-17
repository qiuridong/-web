"""签到脚本聚合管理面板 · FastAPI 入口。

启动流程见 `进度/设计/后端架构.md` § 9.2:
1. 初始化 loguru
2. 加载 settings 缓存(ensure_defaults)
3. 初始化 DB engine + 应用 PRAGMA
4. 运行 alembic upgrade head(由 docker entrypoint 承担时此步骤可跳)
5. 加载/生成 Fernet key
6. 启动 NotificationService(apprise 实例池)— 6B agent 接入
7. 启动 SchedulerService:
   a. 注册内置周期任务(scan_scripts / resume_paused / housekeeping)
   b. 若 settings.script_scan_on_startup 执行一次同步扫描
   c. 加载所有 enabled instance 注册到调度器
   d. scheduler.start()
8. 挂载路由
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from loguru import logger

from app.api.router import api_router
from app.config import get_settings
from app.core.crypto import get_cipher
from app.core.logging import configure_logging
from app.db.session import SessionLocal, dispose_engine
from app.middleware.csrf import CSRFMiddleware
from app.middleware.error_handler import register_exception_handlers
from app.middleware.request_log import RequestLogMiddleware
from app.runner.log_broker import get_log_broker
from app.scheduler.engine import SchedulerService

_APP_VERSION = "0.1.0"

# ============================================================
# 模块级 scheduler 引用 — 给 APScheduler job 回调 / 测试用
# (FastAPI Depends 系统在 cron job 回调里拿不到 request)
# ============================================================
_app_scheduler: SchedulerService | None = None


def get_app_scheduler() -> SchedulerService:
    """供 ``app.deps.get_scheduler_service`` 用 —— 模块级单例。"""
    if _app_scheduler is None:
        raise RuntimeError("Scheduler 尚未初始化")
    return _app_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """应用生命周期钩子 — 启动时初始化,关闭时清理。"""
    global _app_scheduler
    settings = get_settings()

    # ===== startup =====
    configure_logging(level=settings.log_level, logs_dir=settings.logs_dir)
    logger.info(
        "签到管家后端启动 environment={} version={} port={}",
        settings.environment,
        _APP_VERSION,
        settings.port,
    )

    # 提前加载/生成 Fernet 密钥(若不存在,会自动生成 + 强警告日志提示备份)
    get_cipher()

    # 预置 settings(retention_days / timezone / 等 11 项;详见 § 1.8)
    try:
        from app.services import settings_service  # noqa: PLC0415

        with SessionLocal() as _boot_db:
            inserted = settings_service.ensure_defaults(_boot_db)
            _boot_db.commit()
            if inserted:
                logger.info("启动期 ensure_defaults 插入 {} 项预置设置", inserted)
    except Exception as exc:  # noqa: BLE001
        logger.warning("启动期 ensure_defaults 失败(跳过) err={}", exc)

    # 启动期同步扫描一次 scripts/(若启用)
    try:
        from app.services import script_service  # noqa: PLC0415

        with SessionLocal() as db:
            result = script_service.scan_all(db, settings.scripts_dir.resolve())
            db.commit()
            if (
                result["added"]
                or result["updated"]
                or result["removed"]
                or result["errors"]
            ):
                logger.info(
                    "启动扫描完成 added={} updated={} removed={} errors={}",
                    len(result["added"]),
                    len(result["updated"]),
                    len(result["removed"]),
                    len(result["errors"]),
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning("启动扫描失败: {}", exc)

    # 启动 SchedulerService(先注册内置任务,再加载 enabled instance)
    scheduler = SchedulerService()
    try:
        await scheduler.start()
    except Exception as exc:  # noqa: BLE001
        logger.exception("SchedulerService 启动失败: {}", exc)
    _app_scheduler = scheduler
    app.state.scheduler = scheduler

    yield  # ===== app running =====

    # ===== shutdown =====
    logger.info("签到管家后端开始关闭流程")
    if _app_scheduler is not None:
        try:
            await _app_scheduler.shutdown(wait=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning("scheduler shutdown 异常: {}", exc)
    # 关闭所有 SSE channel
    try:
        get_log_broker().shutdown()
    except Exception as exc:  # noqa: BLE001
        logger.warning("log_broker shutdown 异常: {}", exc)
    dispose_engine()
    logger.info("签到管家后端已关闭")


def create_app() -> FastAPI:
    """FastAPI app 工厂。"""
    settings = get_settings()

    app = FastAPI(
        title="签到管家 API",
        description="签到脚本聚合管理面板 — 后端 API",
        version=_APP_VERSION,
        lifespan=lifespan,
        docs_url="/docs" if settings.expose_docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.expose_docs else None,
    )

    # ===== 中间件 =====
    # 顺序:add_middleware 是栈式(后加的先执行),所以"想最先生效"的最后 add
    # 期望执行顺序:request_log(最外) → csrf → 路由
    # 异常处理器单独注册,不走 middleware
    app.add_middleware(CSRFMiddleware)
    app.add_middleware(RequestLogMiddleware)
    register_exception_handlers(app)

    # ===== 路由 =====
    app.include_router(api_router)

    # ===== 健康检查 =====
    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        """健康检查 — 容器 healthcheck 与 Caddy 反代后端探活共用。"""
        return {
            "status": "ok",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": _APP_VERSION,
        }

    return app


# uvicorn 入口:`uvicorn app.main:app`
app = create_app()
