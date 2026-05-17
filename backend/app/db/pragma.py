"""SQLite PRAGMA 连接钩子。

详见 `进度/设计/后端架构.md` § 9.1。

每个新连接都执行:
- `journal_mode = WAL`        多读单写并发,后端高频读 + 低频写场景最佳
- `synchronous = NORMAL`      WAL 下的安全/性能折衷,生产推荐
- `foreign_keys = ON`         SQLite 默认关闭 FK,必须显式开
- `busy_timeout = 5000`       锁等待 5s 后才报 SQLITE_BUSY
- `cache_size = -20000`       约 20 MiB 页缓存(负数表示 KiB 单位)
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
    """在 engine 上注册 connect 事件,确保每个新连接应用 PRAGMA。

    幂等:多次调用对同一 engine 不会重复触发(SQLAlchemy 内部 set 去重)。
    仅对 SQLite 生效;非 SQLite 引擎调用此函数不会出错,但什么也不做。
    """
    if not engine.url.get_backend_name().startswith("sqlite"):
        return

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection: Any, _connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        try:
            for name, value in _PRAGMAS:
                cursor.execute(f"PRAGMA {name} = {value}")
        finally:
            cursor.close()
