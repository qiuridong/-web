"""请求日志 + trace_id 注入。

实现见 `进度/设计/后端架构.md` § 8.3。

每个请求:
1. 生成 trace_id(短随机串,uuid4 hex 12 字符,避免长 UUID 干扰日志)
2. 注入 `request.state.trace_id`(供 error_handler / 业务代码读取)
3. `loguru.contextualize(trace_id=...)` 让本请求作用域内所有日志自动带 trace_id
4. 记录 access log:method / path / status / duration_ms / trace_id / client_ip
5. 响应头加 `X-Trace-Id`,前端可在错误 toast 里展示便于报障
"""
from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware


def _new_trace_id() -> str:
    """短 trace_id — uuid4 hex 前 16 字符,够用且不喧宾夺主。"""
    return uuid.uuid4().hex[:16]


def _client_ip(request: Request) -> str | None:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    if request.client is not None:
        return request.client.host
    return None


class RequestLogMiddleware(BaseHTTPMiddleware):
    """生成 trace_id + 输出 access log + 加响应头 X-Trace-Id。"""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        trace_id = _new_trace_id()
        request.state.trace_id = trace_id

        start = time.perf_counter()
        # 用 contextualize 让本作用域内 loguru 调用都自动带 trace_id
        with logger.contextualize(trace_id=trace_id):
            try:
                response = await call_next(request)
            except Exception:
                duration_ms = int((time.perf_counter() - start) * 1000)
                logger.exception(
                    "请求异常 method={} path={} duration_ms={}",
                    request.method,
                    request.url.path,
                    duration_ms,
                )
                raise
            else:
                duration_ms = int((time.perf_counter() - start) * 1000)
                # access log 一行(INFO 级)
                logger.info(
                    "{} {} -> {} ({}ms) ip={}",
                    request.method,
                    request.url.path,
                    response.status_code,
                    duration_ms,
                    _client_ip(request) or "-",
                )

        # 响应头(注意要在出 contextualize 后再设,避免 contextvar 解绑)
        response.headers["X-Trace-Id"] = trace_id
        return response
