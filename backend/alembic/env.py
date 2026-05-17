"""Alembic 环境配置。

- 数据库 URL 从 `app.config.get_settings().database_url` 取(优先于 alembic.ini)
- target_metadata = `Base.metadata`,覆盖 app/db/models/ 下所有模型
- 支持 online / offline 两种模式

使用:
    cd backend
    uv run alembic revision --autogenerate -m "create initial tables"
    uv run alembic upgrade head
"""
from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# 让 app 包可被 import(alembic 默认 cwd = backend/)
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.config import get_settings  # noqa: E402
from app.db.base import Base  # noqa: E402

# 关键:导入 models 包,确保所有 ORM 模型注册到 Base.metadata
# Backend-Models agent 在 app/db/models/__init__.py 里追加各模型 import
import app.db.models  # noqa: F401, E402


# ===== Alembic Config =====
config = context.config

# 用 settings 覆盖 alembic.ini 里的占位 URL
_settings = get_settings()
config.set_main_option("sqlalchemy.url", _settings.database_url)

# 配置 logging(若 alembic.ini 里有 [loggers] 段)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 给 autogenerate 用的 metadata
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式:不实际连接 DB,生成 SQL 脚本。

    用法:`alembic upgrade head --sql > migration.sql`
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # SQLite ALTER TABLE 限制 → 必须 batch 模式
        render_as_batch=True,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式:实际连接 DB 执行迁移。"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # SQLite ALTER TABLE 限制 → 必须 batch 模式
            render_as_batch=True,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
