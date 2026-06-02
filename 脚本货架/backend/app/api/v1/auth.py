"""鉴权路由：setup / login / logout / me（session cookie）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models.user import User
from app.deps import get_db, require_user
from app.schemas.auth import (
    LoginRequest,
    MessageResponse,
    SetupRequest,
    SetupStateResponse,
    UserResponse,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookie(response: Response, token: str) -> None:
    s = get_settings()
    response.set_cookie(
        key=s.session_cookie_name,
        value=token,
        httponly=True,
        secure=s.effective_cookie_secure,
        samesite="lax",
        max_age=s.session_ttl_hours_default * 3600,
        path="/",
    )


def _user_resp(user: User) -> UserResponse:
    return UserResponse(
        id=user.id, username=user.username, display_name=user.display_name, is_admin=user.is_admin
    )


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.get("/setup", response_model=SetupStateResponse)
def setup_state(db: Session = Depends(get_db)) -> SetupStateResponse:
    return SetupStateResponse(setup_required=auth_service.is_setup_required(db))


@router.post("/setup", response_model=UserResponse)
def setup(
    payload: SetupRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> UserResponse:
    user = auth_service.create_admin(
        db, username=payload.username, password=payload.password, display_name=payload.display_name
    )
    _user2, token = auth_service.authenticate(
        db,
        username=payload.username,
        password=payload.password,
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    _set_session_cookie(response, token)
    return _user_resp(user)


@router.post("/login", response_model=UserResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> UserResponse:
    user, token = auth_service.authenticate(
        db,
        username=payload.username,
        password=payload.password,
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    _set_session_cookie(response, token)
    return _user_resp(user)


@router.post("/logout", response_model=MessageResponse)
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> MessageResponse:
    token = request.cookies.get(get_settings().session_cookie_name)
    auth_service.revoke_session(db, token)
    db.commit()
    response.delete_cookie(get_settings().session_cookie_name, path="/")
    return MessageResponse(message="已登出")


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(require_user)) -> UserResponse:
    return _user_resp(user)
