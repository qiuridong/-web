"""SQLAlchemy engine + SessionLocal + ``get_db`` 依赖（精简自主项目）。

去掉了 APScheduler jobstore engine，货架只有一个业务库。
首次连接前自动创建 SQLite 文件的父目录，省去到处 mkdir。
"""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db.pragma import install_pragma

_settings = get_settings()


def _ensure_sqlite_parent(database_url: str) -> None:
    """SQLite 文件路径的父目录若不存在则创建（否则首次连接报 unable to open）。"""
    if not database_url.startswith("sqlite") or ":///" not in database_url:
        return
    raw = database_url.split(":///", 1)[1]
    if not raw or raw == ":memory:":
        return
    Path(raw).expanduser().parent.mkdir(parents=True, exist_ok=True)


def _build_engine(database_url: str) -> Engine:
    connect_args: dict[str, object] = {}
    if database_url.startswith("sqlite"):
        _ensure_sqlite_parent(database_url)
        connect_args = {"check_same_thread": False, "timeout": 30}
    engine = create_engine(
        database_url,
        connect_args=connect_args,
        pool_pre_ping=True,
        future=True,
    )
    install_pragma(engine)
    return engine


engine: Engine = _build_engine(_settings.database_url)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db() -> Iterator[Session]:
    """FastAPI 依赖：每请求一个 Session，结束后关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def dispose_engine() -> None:
    """应用关闭时释放连接池。"""
    engine.dispose()
