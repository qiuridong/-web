"""CSRF 中间件 — `X-Requested-With` 头校验。

实现见 `进度/设计/后端架构.md` § 5.4。

策略
----
- GET / HEAD / OPTIONS 直接放行
- 其他方法要求 `X-Requested-With: fetch` 头,缺失 → 403 + code=CSRF_REJECTED
- 与 SameSite=Lax cookie 双保险,避免 CSRF token 复杂度

为什么这条防线有效:
- SameSite=Lax 已挡掉绝大多数跨站 POST(浏览器不带 cookie)
- 顺手再要求自定义 header:HTML form 提交无法添加 `X-Requested-With`,
  浏览器跨域 fetch 会因 preflight 被同源策略拦截
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

# 安全方法不需校验
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# 完全跳过 CSRF 校验的路径前缀(健康检查 / 文档 / OpenAPI / agent API)
# - /api/v1/agent/* 走 Bearer token 鉴权(无浏览器 cookie 风险),CSRF 不适用
_EXEMPT_PREFIXES: tuple[str, ...] = (
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/v1/agent/",  # MVP-1:agent 端 API 走 Bearer auth,豁免 CSRF
)


class CSRFMiddleware(BaseHTTPMiddleware):
    """要求非 GET 请求必须携带 `X-Requested-With: fetch` 头。"""

    HEADER_NAME = "x-requested-with"
    HEADER_VALUE = "fetch"

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        method = request.method.upper()

        # 安全方法 / 豁免路径直接放行
        if method in _SAFE_METHODS:
            return await call_next(request)
        if any(request.url.path.startswith(p) for p in _EXEMPT_PREFIXES):
            return await call_next(request)

        actual = (request.headers.get(self.HEADER_NAME) or "").strip().lower()
        if actual != self.HEADER_VALUE:
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "code": "CSRF_REJECTED",
                        "message": (
                            "缺少或错误的 X-Requested-With 头。"
                            "前端 fetch 请求请加 `X-Requested-With: fetch`。"
                        ),
                        "details": {
                            "expected_header": self.HEADER_NAME,
                            "expected_value": self.HEADER_VALUE,
                        },
                    }
                },
            )

        return await call_next(request)
