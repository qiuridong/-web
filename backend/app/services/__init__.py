"""业务逻辑层 — 纯 Python,不依赖 FastAPI 对象,可单元测试。

约定:
- service 函数的第一参数是 `db: Session`
- 抛业务异常用 `app.core.exceptions.*`,不抛 HTTPException
- 不直接读 cookie/header,所有上下文走参数注入
"""
