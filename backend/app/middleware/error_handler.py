"""全局异常 → 标准错误响应。

实现见 `进度/设计/后端架构.md` § 8.1-8.2。

注册的处理器:
- `AppException`                 → 子类 status_code + to_dict()
- `RequestValidationError`(Pydantic)→ 422 + code=VALIDATION_ERROR + 字段错误数组
- `StarletteHTTPException`       → 透传 status,但用 § 8.2 格式包装
- `Exception`(兜底)             → 500 + code=INTERNAL_ERROR + trace_id

响应统一格式:
```json
{
  "error": {
    "code": "...",
    "message": "...",
    "details": {...},
    "trace_id": "..."
  }
}
```
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from loguru import logger
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

from app.core.exceptions import AppException


def _trace_id_from(request: Request) -> str | None:
    """从 request.state 取 trace_id(由 RequestLogMiddleware 注入)。"""
    return getattr(request.state, "trace_id", None)


def _envelope(
    *,
    code: str,
    message: str,
    details: dict[str, Any] | None,
    trace_id: str | None,
) -> dict[str, Any]:
    """构造 § 8.2 标准错误外层。"""
    payload: dict[str, Any] = {
        "code": code,
        "message": message,
        "details": details or {},
    }
    if trace_id is not None:
        payload["trace_id"] = trace_id
    return {"error": payload}


def register_exception_handlers(app: FastAPI) -> None:
    """挂全局异常处理器到 FastAPI app。

    顺序:具体子类 → 基类 → 兜底 Exception。
    """

    # ===== 业务异常(AppException 及子类)=====
    @app.exception_handler(AppException)
    async def _handle_app_exception(
        request: Request, exc: AppException
    ) -> JSONResponse:
        trace_id = _trace_id_from(request)
        # 把 trace_id 同步到 exc(便于日志记录)
        if exc.trace_id is None:
            exc.trace_id = trace_id

        # 5xx 上日志(WARN+),4xx 仅 INFO
        if exc.status_code >= 500:
            logger.opt(exception=exc).error(
                "AppException [{}] status={} path={} trace_id={}",
                exc.code,
                exc.status_code,
                request.url.path,
                trace_id,
            )
        else:
            logger.info(
                "AppException [{}] status={} path={} trace_id={} message={}",
                exc.code,
                exc.status_code,
                request.url.path,
                trace_id,
                exc.message,
            )

        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(
                code=exc.code,
                message=exc.message,
                details=exc.details,
                trace_id=trace_id,
            ),
        )

    # ===== Pydantic 解析失败(请求体不符合 schema)=====
    @app.exception_handler(RequestValidationError)
    async def _handle_validation(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        trace_id = _trace_id_from(request)
        # 把 errors 简化为更友好的结构
        errors = []
        for err in exc.errors():
            loc = list(err.get("loc", []))
            errors.append(
                {
                    "loc": loc,
                    "type": err.get("type"),
                    "msg": err.get("msg"),
                }
            )
        logger.info(
            "RequestValidationError path={} trace_id={} errors={}",
            request.url.path,
            trace_id,
            len(errors),
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_envelope(
                code="VALIDATION_ERROR",
                message="请求参数校验失败",
                details={"errors": errors},
                trace_id=trace_id,
            ),
        )

    # ===== Starlette HTTPException(404 路由不存在等)=====
    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        trace_id = _trace_id_from(request)
        # detail 可能是 dict 或字符串;统一转字符串
        if isinstance(exc.detail, dict):
            message = str(exc.detail.get("message", exc.detail))
            details = dict(exc.detail)
        else:
            message = str(exc.detail) if exc.detail else "HTTP 错误"
            details = None

        # 简单映射 status → code
        code_map = {
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            405: "METHOD_NOT_ALLOWED",
            413: "PAYLOAD_TOO_LARGE",
            415: "UNSUPPORTED_MEDIA_TYPE",
            429: "RATE_LIMITED",
        }
        code = code_map.get(exc.status_code, f"HTTP_{exc.status_code}")
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(
                code=code,
                message=message,
                details=details,
                trace_id=trace_id,
            ),
            headers=getattr(exc, "headers", None),
        )

    # ===== 兜底 — 任何未捕获异常 =====
    @app.exception_handler(Exception)
    async def _handle_unknown(request: Request, exc: Exception) -> JSONResponse:
        trace_id = _trace_id_from(request)
        logger.opt(exception=exc).error(
            "未捕获异常 type={} path={} trace_id={}",
            type(exc).__name__,
            request.url.path,
            trace_id,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_envelope(
                code="INTERNAL_ERROR",
                message="服务器内部错误,请稍后重试",
                details={},
                trace_id=trace_id,
            ),
        )
