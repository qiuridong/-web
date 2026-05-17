"""ORM 模型集合。

**重要**:所有模型必须在此处 `import`,否则 alembic autogenerate 不会发现它们,
迁移脚本会缺表。

模型清单(对应 `进度/设计/后端架构.md` § 1 八张表):
- `user.py`           § 1.7 users
- `session.py`        § 5.3 sessions(登录态)— 类名 `UserSession`,避免与 SQLAlchemy 冲突
- `script.py`         § 1.2 scripts
- `instance.py`       § 1.3 instances
- `run.py`            § 1.4 runs
- `notification.py`   § 1.5/1.6 notification_channels + notification_rules
- `setting.py`        § 1.8 settings
"""
from __future__ import annotations

from app.db.models.user import User  # noqa: F401
from app.db.models.session import UserSession  # noqa: F401
from app.db.models.script import Script  # noqa: F401
from app.db.models.instance import Instance  # noqa: F401
from app.db.models.run import Run  # noqa: F401
from app.db.models.notification import (  # noqa: F401
    NotificationChannel,
    NotificationRule,
)
from app.db.models.setting import Setting  # noqa: F401

__all__ = [
    "User",
    "UserSession",
    "Script",
    "Instance",
    "Run",
    "NotificationChannel",
    "NotificationRule",
    "Setting",
]
