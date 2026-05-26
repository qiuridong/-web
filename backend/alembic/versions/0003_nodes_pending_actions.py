"""nodes 表加 pending_actions + deployed_scripts(MVP-2 推送同步 + 节点脚本管理)

Revision ID: 0003_pending_actions
Revises: 0002_add_nodes
Create Date: 2026-05-26

设计稿:`进度/变更/2026-05-26-推送同步+运行时保留+PR4.md` § 1

变更
----
1. ``nodes`` 表加 ``pending_actions TEXT NOT NULL DEFAULT '{}'``
   - 存 JSON ``{"sync": ["slug1", "slug2"], "delete": ["slug3"]}``
   - 上传时若选了同步节点 → service 把 slug append 到对应 node 的 sync 列表
   - agent poll 时主面板把它带在 poll response 里(无 task 也带)
   - agent 处理完调 ``/agent/inventory-report`` 清空对应 entry
2. ``nodes`` 表加 ``deployed_scripts TEXT NOT NULL DEFAULT '{}'``
   - 存 JSON ``{"slug": {"sha256": "...", "deployed_at": "ISO"}}``
   - agent 通过 ``inventory-report`` 报告本地实际部署的脚本(单一事实源)
   - 节点详情页用它列 "已部署脚本"

downgrade
---------
- 删上述 2 列(SQLite 用 batch_alter_table)
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0003_pending_actions"
down_revision: str | None = "0002_add_nodes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """加 2 个 JSON-as-TEXT 字段。"""
    with op.batch_alter_table("nodes") as batch_op:
        batch_op.add_column(
            sa.Column(
                "pending_actions",
                sa.Text(),
                nullable=False,
                server_default="{}",
            )
        )
        batch_op.add_column(
            sa.Column(
                "deployed_scripts",
                sa.Text(),
                nullable=False,
                server_default="{}",
            )
        )


def downgrade() -> None:
    """删 2 列(SQLite 用 batch)。"""
    with op.batch_alter_table("nodes") as batch_op:
        batch_op.drop_column("deployed_scripts")
        batch_op.drop_column("pending_actions")
