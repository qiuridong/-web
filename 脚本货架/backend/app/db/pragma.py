"""SQLite PRAGMA 连接钩子（移植自主项目 ``backend/app/db/pragma.py``）。

每个新连接执行：WAL / NORMAL / foreign_keys ON / busy_timeout 5s / 20MiB 缓存。
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import Engine

_PRAGMAS: tuple[tuple[str, str], ...] = (
    ("journal_mode", "WAL"),
    ("synchronous", "NORMAL"),
    ("foreign_keys", "ON"),
    ("busy_timeout", "5000"),
    ("cache_size", "-20000"),
)


def install_pragma(engine: Engine) -> None:
    """在 engine 注册 connect 事件，确保每个新连接应用 PRAGMA。仅对 SQLite 生效。"""
    if not engine.url.get_backend_name().startswith("sqlite"):
        return

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        try:
            for name, value in _PRAGMAS:
                cursor.execute(f"PRAGMA {name} = {value}")
        finally:
            cursor.close()
