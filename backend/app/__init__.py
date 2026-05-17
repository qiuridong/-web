"""签到脚本聚合管理面板 — 后端应用包。

详细架构见 `进度/设计/后端架构.md`。所有子模块按职责分层:
- `core/`        横切关注点(异常、日志、加密、安全工具)
- `db/`          SQLAlchemy 模型与 session
- `schemas/`    Pydantic v2 入参/出参
- `api/`         FastAPI 路由层(薄)
- `services/`   业务逻辑(纯 Python)
- `scheduler/`  APScheduler 集成
- `runner/`     子进程沙箱执行
- `plugins/`    脚本插件 manifest 解析
- `notifications/` 通知 (apprise)
- `middleware/` 鉴权/CSRF/错误/请求日志
- `tasks/`      周期性后台任务
- `utils/`      通用工具
"""
