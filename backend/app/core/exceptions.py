"""应用异常体系。

详见 `进度/设计/后端架构.md` § 8.1 / § 8.2。

设计要点:
- 所有业务异常继承自 `AppException`,带 `code` / `status_code` / `message` / `details` / `trace_id`
- 全部走 `app/middleware/error_handler.py` 统一格式化为 § 8.2 的错误响应
- `details` 用于字段级错误等结构化信息,前端可消费
- `trace_id` 在请求中间件注入(UUID7 / nanoid),写入响应 + 应用日志便于排查
"""
from __future__ import annotations

from typing import Any


class AppException(Exception):
    """所有业务异常的基类。

    子类只需声明 `code` / `status_code` 默认值与可选 `default_message`,
    具体场景实例化时可覆盖 `message` / `details`。
    """

    code: str = "INTERNAL_ERROR"
    status_code: int = 500
    default_message: str = "服务器内部错误"

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> None:
        self.message = message or self.default_message
        self.details = details or {}
        self.trace_id = trace_id
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        """转换为 § 8.2 规定的错误响应 payload。

        外层包一个 `error` 键由 error_handler 中间件负责;此处只返回内层。
        """
        payload: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }
        if self.trace_id is not None:
            payload["trace_id"] = self.trace_id
        return payload


# ============================================================
# 401 — 鉴权失败
# ============================================================
class AuthError(AppException):
    code = "AUTH_ERROR"
    status_code = 401
    default_message = "未授权"


class InvalidCredentials(AuthError):
    code = "INVALID_CREDENTIALS"
    default_message = "用户名或密码错误"


class SessionExpired(AuthError):
    code = "SESSION_EXPIRED"
    default_message = "会话已过期,请重新登录"


class AccountLocked(AuthError):
    code = "ACCOUNT_LOCKED"
    default_message = "账户已被锁定,请稍后再试"


# ============================================================
# 403 — 权限不足
# ============================================================
class PermissionError(AppException):  # noqa: A001 — 与内置同名是有意为之,定义在本模块命名空间
    code = "PERMISSION_DENIED"
    status_code = 403
    default_message = "权限不足"


# ============================================================
# 404 — 资源不存在
# ============================================================
class NotFoundError(AppException):
    code = "NOT_FOUND"
    status_code = 404
    default_message = "资源不存在"


class ScriptNotFound(NotFoundError):
    code = "SCRIPT_NOT_FOUND"
    default_message = "脚本不存在"


class InstanceNotFound(NotFoundError):
    code = "INSTANCE_NOT_FOUND"
    default_message = "实例不存在"


class RunNotFound(NotFoundError):
    code = "RUN_NOT_FOUND"
    default_message = "执行记录不存在"


class ChannelNotFound(NotFoundError):
    code = "CHANNEL_NOT_FOUND"
    default_message = "通知渠道不存在"


class RuleNotFound(NotFoundError):
    code = "RULE_NOT_FOUND"
    default_message = "通知规则不存在"


# ============================================================
# 422 — 业务校验失败(区别于 Pydantic 解析层 422)
# ============================================================
class ValidationError(AppException):
    code = "VALIDATION_ERROR"
    status_code = 422
    default_message = "参数校验失败"


class ConfigSchemaError(ValidationError):
    """实例 config 不符合 manifest fields_schema。"""

    code = "CONFIG_SCHEMA_ERROR"
    default_message = "实例配置不符合脚本字段定义"


class CronExprInvalidError(ValidationError):
    code = "CRON_EXPR_INVALID"
    default_message = "cron 表达式无效"


class ManifestInvalidError(ValidationError):
    code = "MANIFEST_INVALID"
    default_message = "manifest.yaml 校验失败"


# ============================================================
# 409 — 冲突
# ============================================================
class ConflictError(AppException):
    code = "CONFLICT"
    status_code = 409
    default_message = "资源冲突"


class DuplicateName(ConflictError):
    code = "DUPLICATE_NAME"
    default_message = "名称已存在"


class ConcurrentRunConflict(ConflictError):
    """例如 test 与 run 不能同时跑同一 instance。"""

    code = "CONCURRENT_RUN_CONFLICT"
    default_message = "实例已有任务正在执行"


# ============================================================
# 429 — 资源限流
# ============================================================
class ResourceLimitError(AppException):
    code = "RESOURCE_LIMIT"
    status_code = 429
    default_message = "已达到资源上限"


# ============================================================
# 502 — 外部服务失败
# ============================================================
class ExternalServiceError(AppException):
    code = "EXTERNAL_SERVICE_ERROR"
    status_code = 502
    default_message = "外部服务调用失败"


# ============================================================
# 500 — 兜底内部错误
# ============================================================
class InternalError(AppException):
    code = "INTERNAL_ERROR"
    status_code = 500
    default_message = "服务器内部错误"
