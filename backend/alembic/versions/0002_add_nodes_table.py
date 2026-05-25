"""add nodes table + instances.node_id (MVP-1 远程 agent)

Revision ID: 0002_add_nodes
Revises: f9dfb20755b4
Create Date: 2026-05-24

设计稿:`进度/设计/远程VPS脚本执行调研.md` § 7

变更:
1. 新建 ``nodes`` 表:id / slug(unique) / name / description / is_local /
   auth_token_hash / last_seen_at / version / metadata_json / enabled /
   created_at / updated_at
2. ``instances`` 表加 ``node_id INTEGER FK nodes.id ON DELETE SET NULL DEFAULT 1``
3. 插入默认 ``local`` 节点(id=1, slug='local', is_local=1, enabled=1)

downgrade:
- 删 instances.node_id 列(SQLite 用 batch_alter_table)
- 删 nodes 表
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0002_add_nodes"
down_revision: str | None = "f9dfb20755b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ============================================================
    # 1. 新建 nodes 表
    # ============================================================
    op.create_table(
        "nodes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "is_local",
            sa.Boolean(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("auth_token_hash", sa.String(length=128), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.String(length=32), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column(
            "enabled",
            sa.Boolean(),
            server_default="1",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("nodes", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_nodes_slug"), ["slug"], unique=True
        )
        batch_op.create_index(
            batch_op.f("ix_nodes_enabled"), ["enabled"], unique=False
        )

    # ============================================================
    # 2. 插入 default local 节点(id=1)
    # ============================================================
    op.execute(
        """
        INSERT INTO nodes (id, slug, name, description, is_local, enabled,
                           created_at, updated_at)
        VALUES (1, 'local', '本地节点', '主面板自身,执行所有未指定远程节点的实例',
                1, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """
    )

    # ============================================================
    # 3. instances 表加 node_id 列
    # ============================================================
    # 注:SQLite batch_alter_table 会 rebuild 整个表,要把 FK / index 一并加
    with op.batch_alter_table("instances", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "node_id",
                sa.Integer(),
                server_default="1",
                nullable=True,  # SQLite 不允许 NOT NULL + 后加 FK,留 nullable;app 层默认 1
            )
        )
        batch_op.create_foreign_key(
            "fk_instances_node_id",
            "nodes",
            ["node_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            batch_op.f("ix_instances_node_id"), ["node_id"], unique=False
        )

    # 把现有 instance 行的 node_id 设为 1(server_default 只对新行生效)
    op.execute("UPDATE instances SET node_id = 1 WHERE node_id IS NULL")


def downgrade() -> None:
    # 反向:先删 instances.node_id,再删 nodes 表
    with op.batch_alter_table("instances", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_instances_node_id"))
        batch_op.drop_constraint("fk_instances_node_id", type_="foreignkey")
        batch_op.drop_column("node_id")

    with op.batch_alter_table("nodes", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_nodes_enabled"))
        batch_op.drop_index(batch_op.f("ix_nodes_slug"))

    op.drop_table("nodes")
