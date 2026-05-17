"""鉴权中间件 — session cookie → 当前用户。

TODO(Batch 2 / Backend-Auth): 实现见 `进度/设计/后端架构.md` § 5.3。

流程:
1. 从 cookie 取 settings.session_cookie_name(默认 `sid`)
2. 查 sessions 表;过期或不存在 → 401(放行 🔓 路径见白名单)
3. 注入 request.state.user / request.state.session
4. 触发 last_used_at 更新(可批量,避免每次写)

🔓 白名单(无需 session):
- /health
- /docs / /openapi.json / /redoc
- /api/v1/auth/setup-status / /auth/setup / /auth/login
"""
from __future__ import annotations
