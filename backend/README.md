# 签到管家 — 后端

FastAPI + APScheduler + SQLite(WAL) 的最小后端骨架。

详细设计见仓库根 `进度/设计/后端架构.md`。

## 本地开发

```bash
# 1. 创建 venv(Python 3.12,与 Dockerfile 对齐)
uv venv --python 3.12

# 2. 装依赖(含 dev)
uv pip install -e ".[dev]"

# 3. 数据库迁移
uv run alembic upgrade head

# 4. 启动开发服务器(必须 --workers 1,APScheduler 同进程模式)
uv run uvicorn app.main:app --reload --port 8000 --workers 1

# 5. 跑测试
uv run pytest

# 6. 代码检查
uv run ruff check .
uv run ruff format .
uv run mypy app
```

启动后访问:
- `http://localhost:8000/docs` — OpenAPI 文档(开发模式)
- `http://localhost:8000/health` — 健康检查
- `http://localhost:8000/api/v1/...` — 业务路由(详见 `进度/设计/后端架构.md` § 2)

## 目录结构

详见 `进度/设计/后端架构.md` § 6;一句话总结:`app/{core,db,schemas,api,services,scheduler,runner,plugins,notifications,middleware,tasks,utils}`。

## 关键约束(违反会出大事)

- **uvicorn `--workers 1`** — APScheduler 同进程模式,多 worker 会重复触发任务
- **`data/encryption.key`** 不入 git / 不入镜像 / 不入日志 — 主密钥泄露 = 所有加密配置作废
- **secret 字段** GET 响应必须自动脱敏为 `null` + `_secret_set: bool`
- **删除 `scripts/<slug>/` 磁盘文件** 不在 API 范围内 — DELETE 接口只删 DB 行

## 数据库迁移

新增/修改模型后:

```bash
uv run alembic revision --autogenerate -m "add foo column"
# 检查生成的迁移脚本(SQLite 用 batch 模式,某些 op 需手工调整)
uv run alembic upgrade head
```
