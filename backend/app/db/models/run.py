"""Run ORM 模型 — `runs` 表(执行历史,写入最频繁,索引最关键)。

实现见 `进度/设计/后端架构.md` § 1.4。

字段:id / instance_id (FK ON DELETE CASCADE) / script_slug (冗余) /
      trigger_type (manual/scheduled/retry/api) /
      trigger_user_id (FK users.id ON DELETE SET NULL) /
      parent_run_id (FK runs.id, retry 链) /
      status (pending/running/success/failure/error/timeout/cancelled) /
      exit_code / result_message / result_data_json /
      stdout / stderr / stdout_truncated / stderr_truncated /
      started_at / finished_at / duration_ms / host / created_at

索引(关键):
  - ix_runs_instance_started (instance_id, started_at DESC)
  - ix_runs_started_at (started_at DESC)
  - ix_runs_status_started (status, started_at DESC)
  - ix_runs_script_started (script_slug, started_at DESC)
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.instance import Instance
    from app.db.models.user import User


class Run(Base):
    """脚本执行历史(单次)。

    高频查询模式与对应索引:
    1. 某 instance 的最近 N 条 → `ix_runs_instance_started (instance_id, started_at DESC)`
    2. 全局最近 N 条          → `ix_runs_started_at (started_at DESC)`
    3. 失败筛选                → `ix_runs_status_started (status, started_at DESC)`
    4. 按脚本聚合统计          → `ix_runs_script_started (script_slug, started_at DESC)`

    `stdout`/`stderr` 各设上限,默认 `max_log_bytes = 256 KiB`,超出尾部截断。
    """

    __tablename__ = "runs"
    __table_args__ = (
        Index("ix_runs_instance_started", "instance_id", "started_at"),
        Index("ix_runs_started_at", "started_at"),
        Index("ix_runs_status_started", "status", "started_at"),
        Index("ix_runs_script_started", "script_slug", "started_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instance_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("instances.id", ondelete="CASCADE"),
        nullable=False,
    )
    # script_slug 冗余:即便 instance 删了便于按脚本统计;也用于不 join 的快速筛选
    script_slug: Mapped[str] = mapped_column(String(64), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(16), nullable=False)
    trigger_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    parent_run_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("runs.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_message: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # JSON 字段:存 Text,应用层 json.dumps/loads
    result_data_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    stdout: Mapped[str | None] = mapped_column(Text, nullable=True)
    stderr: Mapped[str | None] = mapped_column(Text, nullable=True)
    stdout_truncated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    stderr_truncated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    host: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # ===== 关系 =====
    # back_populates 指向 instance.runs,foreign_keys 显式区分(因 instances.last_run_id 也指向 runs.id)
    instance: Mapped[Instance] = relationship(
        "Instance",
        back_populates="runs",
        foreign_keys=[instance_id],
    )
    trigger_user: Mapped[User | None] = relationship(
        "User",
        foreign_keys=[trigger_user_id],
    )
    parent_run: Mapped[Run | None] = relationship(
        "Run",
        remote_side="Run.id",
        foreign_keys=[parent_run_id],
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Run id={self.id} instance_id={self.instance_id} status={self.status!r}>"
