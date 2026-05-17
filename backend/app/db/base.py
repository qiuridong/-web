"""SQLAlchemy 2 declarative base。

所有 ORM 模型继承 `Base`,通过 `Base.metadata` 喂给 alembic autogenerate。
"""
from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """所有 ORM 模型的统一基类。

    SQLAlchemy 2.x 风格:用 `Mapped[]` + `mapped_column()` 声明列,
    见 `进度/设计/后端架构.md` § 1 各表定义。
    """
