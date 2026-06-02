"""聚合 API 路由（前缀 /api）。"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import auth, scripts

api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router)
api_router.include_router(scripts.router)
