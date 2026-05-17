"""鉴权 API — `/api/v1/auth/*`。

实现见 `进度/设计/后端架构.md` § 2.1 + § 5.3。

端点清单(6 个):
- GET    /auth/setup-status      🔓
- POST   /auth/setup             🔓 仅 users 表为空时可用;成功后自动登录
- POST   /auth/login             🔓 成功设置 session cookie
- POST   /auth/logout            🔒 销毁 session;204
- GET    /auth/me                🔒 当前用户信息
- POST   /auth/change-password   🔒 改密成功后强制重新登录(撤销所有 session)

所有失败抛 `app.core.exceptions.*`,由 error_handler 中间件统一格式化为 § 8.2。
"""
from __future__ import annotations

from fastapi import APIRouter, Request, Response, status
from loguru import logger

from app.config import get_settings
from app.core.exceptions import (
    AuthError,
    ConflictError,
    ValidationError,
)
from app.db.models.user import User
from app.deps import CurrentUser, DBSession, OptionalSessionToken
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    SetupRequest,
    SetupStatusResponse,
    UserResponse,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


# ============================================================
# Helpers
# ============================================================
def _get_client_ip(request: Request) -> str | None:
    """取客户端 IP — 优先 X-Forwarded-For 第一段(Caddy 反代会设置)。"""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    if request.client is not None:
        return request.client.host
    return None


def _set_session_cookie(response: Response, token: str) -> None:
    """设置 session cookie(HttpOnly / Secure(prod) / SameSite=Lax)。"""
    settings = get_settings()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_ttl_hours_default * 3600,
        path="/",
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
    )


def _clear_session_cookie(response: Response) -> None:
    """清除 session cookie(登出 / 改密)。"""
    settings = get_settings()
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
    )


# ============================================================
# 端点实现
# ============================================================
@router.get(
    "/setup-status",
    response_model=SetupStatusResponse,
    summary="是否需要首次初始化",
)
def setup_status(db: DBSession) -> SetupStatusResponse:
    """🔓 返回 `{ "needs_setup": bool }`。

    needs_setup=true 时前端跳"首次设置密码"页。
    """
    return SetupStatusResponse(needs_setup=auth_service.is_setup_required(db))


@router.post(
    "/setup",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="首次创建管理员",
)
def setup(
    payload: SetupRequest,
    request: Request,
    response: Response,
    db: DBSession,
) -> LoginResponse:
    """🔓 仅当用户表为空时可调用;成功后自动登录(设置 cookie)。

    服务端会**二次检查**用户表为空,防 race。
    """
    settings = get_settings()
    ip = _get_client_ip(request)
    user_agent = request.headers.get("user-agent")

    # 创建用户(create_admin 内部已二次检查表为空)
    try:
        user = auth_service.create_admin(
            db,
            username=payload.username,
            password=payload.password,
            display_name=payload.display_name,
        )
    except ConflictError:
        # 转 403:"已初始化,无法 setup" 比 409 更直观,业务上也是权限不足
        # 设计稿 § 2.1 未规定具体码,我们用 403 + ALREADY_INITIALIZED
        # 但 ConflictError 默认是 409,更准确。我们就保留 409,与 zod schema 一致。
        raise

    # 自动登录:写一条 session
    _, token = auth_service.authenticate(
        db,
        username=user.username,
        password=payload.password,
        ip=ip,
        user_agent=user_agent,
        ttl_hours=settings.session_ttl_hours_default,
    )

    # 提交 — db 在请求结束自动 close,但 setup 这种关键写入需要显式 commit
    db.commit()
    db.refresh(user)

    _set_session_cookie(response, token)
    logger.info("setup 完成,自动登录 user_id={}", user.id)
    return LoginResponse(user=UserResponse.model_validate(user))


@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="登录",
)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: DBSession,
) -> LoginResponse:
    """🔓 用户名 + 密码登录,成功后设置 session cookie。

    失败抛 `InvalidCredentials`(401);锁定抛 `AccountLocked`(401)。
    """
    settings = get_settings()
    ip = _get_client_ip(request)
    user_agent = request.headers.get("user-agent")

    user, token = auth_service.authenticate(
        db,
        username=payload.username,
        password=payload.password,
        ip=ip,
        user_agent=user_agent,
        ttl_hours=settings.session_ttl_hours_default,
    )
    db.commit()
    db.refresh(user)

    _set_session_cookie(response, token)
    return LoginResponse(user=UserResponse.model_validate(user))


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="登出",
)
def logout(
    request: Request,
    response: Response,
    db: DBSession,
    token: OptionalSessionToken,
) -> Response:
    """🔒 销毁当前 session 并清 cookie。返回 204。

    设计上 logout 应需要 session,但若 cookie 缺失或已过期,
    我们也照常清 cookie 返回 204(幂等)。
    所以**此端点不强制 `CurrentUser`**,但仍受 CSRF 中间件约束(非 GET)。
    """
    auth_service.revoke_session(db, token)
    db.commit()
    _clear_session_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get(
    "/me",
    response_model=UserResponse,
    summary="当前用户信息",
)
def me(current_user: CurrentUser) -> UserResponse:
    """🔒 返回当前登录用户。"""
    user = current_user  # type: ignore[assignment]  # 实际是 User
    return UserResponse.model_validate(user)


@router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="修改密码(成功后强制重新登录)",
)
def change_password(
    payload: ChangePasswordRequest,
    response: Response,
    db: DBSession,
    current_user: CurrentUser,
) -> Response:
    """🔒 修改密码;成功后撤销所有 session,清 cookie,前端需重新登录。"""
    user: User = current_user  # type: ignore[assignment]

    auth_service.change_password(
        db,
        user=user,
        old_password=payload.old_password,
        new_password=payload.new_password,
    )
    db.commit()

    _clear_session_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
