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

    # 2.5 轻量 schema 演进：旧库补 category 列（create_all 不改已存在表）+ 已知脚本默认归类
    from sqlalchemy import text, update

    from app.db.models.script import HubScript
    from app.db.session import SessionLocal

    with engine.connect() as conn:
        _cols = [r[1] for r in conn.execute(text("PRAGMA table_info(hub_scripts)"))]
        if "category" not in _cols:
            conn.execute(text("ALTER TABLE hub_scripts ADD COLUMN category VARCHAR(32)"))
            conn.commit()
            logger.info("schema 演进：hub_scripts 补 category 列")

    # 3. 种子导入（幂等，首启把初始库存灌进库）
    try:
        from app.services.seed import seed_initial_scripts

        count = seed_initial_scripts()
        if count:
            logger.info("种子导入 {} 个脚本", count)
    except Exception as exc:  # noqa: BLE001
        logger.warning("种子导入跳过: {}", exc)

    # 4. 已知脚本默认归类（种子入库后，仅对仍未分类的设；用户改过的不动）
    with SessionLocal() as _db:
        for _slug, _cat in {"ptfans": "PT站", "jmcomic": "漫画动漫", "coklw": "论坛社区"}.items():
            _db.execute(
                update(HubScript)
                .where(HubScript.slug == _slug, HubScript.category.is_(None))
                .values(category=_cat)
            )
        _db.commit()

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

    # CORS：货架是公共脚本仓库 —— 读接口（GET/HEAD/OPTIONS）对任意来源开放，
    # 任何人在自己 VPS 部署的签到管家都能跨域读列表 / 拉 bundle / 取 icon；
    # 写操作（POST/PUT/DELETE）不在放行方法内 → 只能由货架自己前端同源登录后操作，
    # 别人无法跨域写。allow_credentials=False 与 "*" 兼容（读公开不需带 cookie）。
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["GET", "HEAD", "OPTIONS"],
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
