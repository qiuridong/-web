"""FastAPI 依赖：DB 会话 + 登录态（写操作鉴权门）。"""
from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models.user import User
from app.db.session import get_db
from app.services import auth_service

__all__ = ["get_db", "require_user"]


def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    """要求已登录（读 cookie → verify_session）。未登录/过期抛 401。"""
    token = request.cookies.get(get_settings().session_cookie_name)
    return auth_service.verify_session(db, token)
