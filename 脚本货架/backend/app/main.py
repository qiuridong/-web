"""脚本货架 FastAPI 应用入口。"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from app.api.router import api_router
from app.config import get_settings
from app.core.exceptions import AppException
from app.db.session import dispose_engine, engine

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # 1. 确保运行时目录存在
    for d in (settings.app_data_dir, settings.scripts_dir, settings.logs_dir):
        Path(d).mkdir(parents=True, exist_ok=True)

    # 2. 建表（幂等；正式部署也可用 alembic，create_all 只建缺失表）
    from app.db import models  # noqa: F401 — 触发全部 model 注册
    from app.db.base import Base

    Base.metadata.create_all(bind=engine)

    # 3. 种子导入（幂等，首启把初始库存灌进库）
    try:
        from app.services.seed import seed_initial_scripts

        count = seed_initial_scripts()
        if count:
            logger.info("种子导入 {} 个脚本", count)
    except Exception as exc:  # noqa: BLE001
        logger.warning("种子导入跳过: {}", exc)

    logger.info("脚本货架启动完成 env={} docs={}", settings.environment, settings.is_docs_exposed())
    yield
    dispose_engine()


def create_app() -> FastAPI:
    app = FastAPI(
        title="脚本货架",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.is_docs_exposed() else None,
        openapi_url="/openapi.json" if settings.is_docs_exposed() else None,
        redoc_url=None,
    )

    # CORS：M3 允许签到管家前端跨域直读货架列表
    origins = settings.cors_origin_list
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.exception_handler(AppException)
    async def _handle_app_exception(_request: Request, exc: AppException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"error": exc.to_dict()})

    @app.get("/health", tags=["meta"])
    def health() -> dict:
        return {"status": "ok", "app": settings.app_name}

    app.include_router(api_router)
    return app


app = create_app()
