"""HTTP 中间件 — 鉴权、CSRF、错误处理、请求日志。

详见 `进度/设计/后端架构.md` § 5.3-5.4 + § 8.1-8.2。

挂载顺序敏感(从外到内):
  RequestLogMiddleware → ErrorHandler(register_exception_handlers) →
  CSRFMiddleware → AuthMiddleware
"""
