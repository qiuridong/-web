"""数据库访问层。

- `base.py`     SQLAlchemy 2 DeclarativeBase
- `session.py`  engine / SessionLocal / get_db 依赖
- `pragma.py`   SQLite WAL 等 PRAGMA 钩子
- `models/`     ORM 模型(每个表一个模块)

详见 `进度/设计/后端架构.md` § 1、§ 9.1。
"""
