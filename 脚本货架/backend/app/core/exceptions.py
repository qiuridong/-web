"""应用异常体系（精简自主项目 ``backend/app/core/exceptions.py``）。

所有业务异常继承 :class:`AppException`，带 ``code`` / ``status_code`` /
``message`` / ``details``，由 ``main.py`` 的异常处理器统一格式化为
``{"error": {...}}`` 响应。
"""
from __future__ import annotations

from typing import Any


class AppException(Exception):
    """所有业务异常的基类。"""

    code: str = "INTERNAL_ERROR"
    status_code: int = 500
    default_message: str = "服务器内部错误"

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.default_message
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


# ===== 401 鉴权 =====
class AuthError(AppException):
    code = "AUTH_ERROR"
    status_code = 401
    default_message = "未授权"


class InvalidCredentials(AuthError):
    code = "INVALID_CREDENTIALS"
    default_message = "用户名或密码错误"


class SessionExpired(AuthError):
    code = "SESSION_EXPIRED"
    default_message = "会话已过期，请重新登录"


class AccountLocked(AuthError):
    code = "ACCOUNT_LOCKED"
    default_message = "账户已被锁定，请稍后再试"


# ===== 403 权限 =====
class PermissionError(AppException):  # noqa: A001 — 与内置同名是有意为之
    code = "PERMISSION_DENIED"
    status_code = 403
    default_message = "权限不足"


# ===== 404 不存在 =====
class NotFoundError(AppException):
    code = "NOT_FOUND"
    status_code = 404
    default_message = "资源不存在"


class ScriptNotFound(NotFoundError):
    code = "SCRIPT_NOT_FOUND"
    default_message = "脚本不存在"


# ===== 422 校验 =====
class ValidationError(AppException):
    code = "VALIDATION_ERROR"
    status_code = 422
    default_message = "参数校验失败"


class ManifestInvalidError(ValidationError):
    code = "MANIFEST_INVALID"
    default_message = "manifest.yaml 校验失败"


# ===== 409 冲突 =====
class ConflictError(AppException):
    code = "CONFLICT"
    status_code = 409
    default_message = "资源冲突"


class DuplicateName(ConflictError):
    code = "DUPLICATE_NAME"
    default_message = "名称已存在"


# ===== 413 请求体过大 =====
class PayloadTooLarge(AppException):
    code = "PAYLOAD_TOO_LARGE"
    status_code = 413
    default_message = "请求体过大"


# ===== 500 兜底 =====
class InternalError(AppException):
    code = "INTERNAL_ERROR"
    status_code = 500
    default_message = "服务器内部错误"
