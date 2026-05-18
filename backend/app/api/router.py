"""v1 路由聚合 — 所有子路由挂到 `/api/v1` 前缀下。

详见 `进度/设计/后端架构.md` § 2(36 个端点完整清单)。

子路由由各 Backend-API agent 实现具体处理函数;此处只负责聚合 include。
即便子路由暂时是空 `APIRouter`,也要 include,确保 OpenAPI 路径正确分组。
"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    auth,
    dashboard,
    instances,
    notifications,
    runs,
    script_upload,
    scripts,
    settings,
)


api_router = APIRouter(prefix="/api/v1")

# 顺序按设计稿 § 2.1 → 2.7
api_router.include_router(auth.router)
api_router.include_router(scripts.router)
# MVP-5:上传 + 在线编辑端点,与 scripts.router 共享 /scripts 前缀
api_router.include_router(script_upload.router)
api_router.include_router(instances.router)
api_router.include_router(runs.router)
api_router.include_router(notifications.router)
api_router.include_router(settings.router)
api_router.include_router(dashboard.router)
