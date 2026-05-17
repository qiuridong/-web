"""SQLAlchemy engine + SessionLocal + `get_db` 依赖。

详见 `进度/设计/后端架构.md` § 9.1 / § 9.2。
"""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db.pragma import install_pragma

# ===== 模块级单例 =====
_settings = get_settings()


def _build_engine(database_url: str) -> Engine:
    """构建 SQLAlchemy engine。

    SQLite 专属优化:
    - `check_same_thread=False`:允许跨线程使用(FastAPI dependency 在不同线程释放)
    - `timeout=30`:DB-API 层等待锁的秒数(配合 PRAGMA busy_timeout)
    - `pool_pre_ping=True`:连接复用前 ping 一下,避免 stale connection
    """
    connect_args: dict[str, object] = {}
    if database_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False, "timeout": 30}

    engine = create_engine(
        database_url,
        connect_args=connect_args,
        pool_pre_ping=True,
        future=True,  # SQLAlchemy 2.x 风格(冗余,2.0+ 默认)
    )
    install_pragma(engine)
    return engine


# 业务库 engine
engine: Engine = _build_engine(_settings.database_url)

# Session 工厂(autoflush 关闭 — 要让 service 层显式 flush/commit)
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db() -> Iterator[Session]:
    """FastAPI 依赖:每个请求获取一个 Session,请求结束后关闭。

    用法::

        from fastapi import Depends
        from app.db.session import get_db
        from sqlalchemy.orm import Session

        @router.get("/foo")
        def foo(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def dispose_engine() -> None:
    """应用关闭时调用,释放连接池。"""
    engine.dispose()
