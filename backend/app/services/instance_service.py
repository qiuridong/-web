"""实例 service — CRUD + 配置加解密 + 与调度器同步。

实现见 `进度/设计/后端架构.md` § 2.3 + § 4.3 + § 5.2。

公开函数
--------
- :func:`list_instances` 分页列表 + 可选筛选
- :func:`create_instance` 校验 + 加密 + 注册 scheduler
- :func:`get_instance` / :func:`get_instance_detail`(后者带脱敏)
- :func:`update_instance` PATCH;secret 字段未提交保留原值;cron 变化时 reschedule
- :func:`delete_instance` 摘 job + 级联删 runs
- :func:`enable_instance` / :func:`disable_instance`
- :func:`pause_instance` / :func:`resume_instance`
- :func:`trigger_instance` 立即触发,返回 ``run_id``
- :func:`test_instance` 试运行,不写 runs 不发通知

设计要点
--------
- 加密走 :func:`app.core.crypto.get_cipher`,永远不让明文 secret 入日志/DB
- service 层负责 ``db.flush()``,事务提交交给路由层
- 异常用 ``app.core.exceptions.*``
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from loguru import logger
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.crypto import FernetCipher, get_cipher
from app.core.exceptions import (
    ConcurrentRunConflict,
    ConflictError,
    CronExprInvalidError,
    InstanceNotFound,
    ScriptNotFound,
    ValidationError,
)
from app.db.models.instance import Instance
from app.db.models.run import Run
from app.db.models.script import Script
from app.plugins.fields import mask_secrets, merge_secrets, validate_config
from app.plugins.manifest import ManifestField
from app.scheduler.executor import execute_run, run_instance_test

if TYPE_CHECKING:
    from app.scheduler.engine import SchedulerService


# ============================================================
# 辅助
# ============================================================
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _validate_cron_expr(expr: str | None) -> None:
    """audit High #10:cron 写库前先校验合法性。

    用 APScheduler 的 ``CronTrigger.from_crontab`` 做语义解析,失败立即抛
    ``CronExprInvalidError`` 422,不让非法 cron 进库 → scheduler 不再炸。

    :raises CronExprInvalidError: cron 字符串语义非法
    """
    if expr is None:
        return
    expr = expr.strip()
    if not expr:
        return
    try:
        from apscheduler.triggers.cron import CronTrigger  # noqa: PLC0415

        CronTrigger.from_crontab(expr)
    except (ValueError, KeyError) as exc:
        raise CronExprInvalidError(
            f"cron 表达式非法: {exc}",
            details={"cron_expr": expr, "reason": str(exc)},
        ) from exc


def _load_fields(script: Script) -> list[ManifestField]:
    """从 ``script.fields_schema_json`` 反序列化为 ManifestField 列表。"""
    import json as _json

    raw = _json.loads(script.fields_schema_json or "[]")
    if not isinstance(raw, list):
        return []
    return [ManifestField.model_validate(item) for item in raw]


def _get_instance_or_404(db: Session, instance_id: int) -> Instance:
    inst = db.scalars(
        select(Instance).where(Instance.id == instance_id)
    ).one_or_none()
    if inst is None:
        raise InstanceNotFound(
            f"未找到 ID 为 {instance_id} 的实例",
            details={"instance_id": instance_id},
        )
    return inst


def _get_script_by_slug_or_404(db: Session, slug: str) -> Script:
    script = db.scalars(select(Script).where(Script.slug == slug)).one_or_none()
    if script is None:
        raise ScriptNotFound(
            f"脚本不存在: {slug!r}",
            details={"slug": slug},
        )
    return script


def _serialize_instance_for_detail(
    instance: Instance,
    script: Script,
    cipher: FernetCipher,
) -> dict[str, Any]:
    """组装详情 dict — 解密 config + 脱敏 secret + 携带 script brief。

    返回字段对齐 :class:`app.schemas.instance.InstanceDetail`。
    """
    # 解密
    if instance.config_blob:
        try:
            raw_config = cipher.decrypt_dict(instance.config_blob)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "instance.{} config 解密失败: {}",
                instance.id,
                exc,
            )
            raw_config = {}
    else:
        raw_config = {}

    # 脱敏
    fields = _load_fields(script)
    masked, secret_set = mask_secrets(raw_config, fields)

    return {
        "id": instance.id,
        "name": instance.name,
        "description": instance.description,
        "script": {"slug": script.slug, "name": script.name},
        "cron_expr": instance.cron_expr,
        "timeout_sec": instance.timeout_sec,
        "enabled": instance.enabled,
        "paused_until": instance.paused_until,
        "max_retries": instance.max_retries,
        "retry_interval_sec": instance.retry_interval_sec,
        "last_run_id": instance.last_run_id,
        "last_run_status": instance.last_run_status,
        "last_run_at": instance.last_run_at,
        "next_run_at": instance.next_run_at,
        "total_runs": instance.total_runs,
        "total_successes": instance.total_successes,
        "created_at": instance.created_at,
        "updated_at": instance.updated_at,
        "config": masked,
        "_secret_set": secret_set,
    }


def _serialize_instance_for_list(
    instance: Instance, script: Script
) -> dict[str, Any]:
    """组装列表 dict — 不含 config,无解密成本。"""
    return {
        "id": instance.id,
        "name": instance.name,
        "description": instance.description,
        "script": {"slug": script.slug, "name": script.name},
        "cron_expr": instance.cron_expr,
        "timeout_sec": instance.timeout_sec,
        "enabled": instance.enabled,
        "paused_until": instance.paused_until,
        "last_run_id": instance.last_run_id,
        "last_run_status": instance.last_run_status,
        "last_run_at": instance.last_run_at,
        "next_run_at": instance.next_run_at,
        "total_runs": instance.total_runs,
        "total_successes": instance.total_successes,
    }


# ============================================================
# 列表
# ============================================================
def list_instances(
    db: Session,
    *,
    script_slug: str | None = None,
    enabled: bool | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    """分页列表 + 可选过滤。

    :param script_slug: 仅返回此 slug 的实例
    :param enabled: 启用状态过滤
    :param status: 按 ``last_run_status`` 过滤
    :returns: (序列化后的 dict 列表, total)
    """
    stmt = select(Instance, Script).join(Script, Instance.script_id == Script.id)
    count_stmt = (
        select(func.count())
        .select_from(Instance)
        .join(Script, Instance.script_id == Script.id)
    )

    if script_slug is not None:
        stmt = stmt.where(Script.slug == script_slug)
        count_stmt = count_stmt.where(Script.slug == script_slug)
    if enabled is not None:
        stmt = stmt.where(Instance.enabled == enabled)
        count_stmt = count_stmt.where(Instance.enabled == enabled)
    if status:
        stmt = stmt.where(Instance.last_run_status == status)
        count_stmt = count_stmt.where(Instance.last_run_status == status)

    total = int(db.execute(count_stmt).scalar_one())
    offset = max(0, (page - 1) * page_size)
    stmt = stmt.order_by(Instance.id.desc()).offset(offset).limit(page_size)

    items: list[dict[str, Any]] = []
    for inst, script in db.execute(stmt).all():
        items.append(_serialize_instance_for_list(inst, script))

    return items, total


# ============================================================
# 创建
# ============================================================
def create_instance(
    db: Session,
    *,
    payload: Any,
    cipher: FernetCipher,
    scheduler: "SchedulerService | None" = None,
) -> dict[str, Any]:
    """创建实例 — 校验 config → 加密 → 落库 → 注册到 scheduler。

    :param payload: ``schemas.instance.InstanceCreate`` 实例
    :returns: 详情 dict(可直接 ``InstanceDetail.model_validate``)
    """
    # 1. 找脚本
    script = _get_script_by_slug_or_404(db, payload.script_slug)

    # audit High #10:cron 写库前校验(create / update 都做)
    if payload.cron_expr is not None:
        _validate_cron_expr(payload.cron_expr)

    # 2. 校验 config
    fields = _load_fields(script)
    try:
        cleaned_config = validate_config(payload.config or {}, fields)
    except Exception:
        raise  # ConfigSchemaError → error_handler

    # 3. 名称重名校验(同 script 下 name 唯一)
    dup = db.scalars(
        select(Instance).where(
            Instance.script_id == script.id, Instance.name == payload.name
        )
    ).one_or_none()
    if dup is not None:
        raise ConflictError(
            f"该脚本下已存在同名实例: {payload.name!r}",
            details={"script_slug": script.slug, "name": payload.name},
        )

    # 4. 加密
    config_blob = cipher.encrypt_dict(cleaned_config) if cleaned_config else ""

    # 5. 落库
    instance = Instance(
        script_id=script.id,
        name=payload.name,
        description=payload.description,
        cron_expr=payload.cron_expr,
        timeout_sec=payload.timeout_sec,
        enabled=True,  # 创建即启用,后续可通过 enable/disable 切换
        max_retries=payload.max_retries,
        retry_interval_sec=payload.retry_interval_sec,
        config_blob=config_blob,
        config_version=1,
    )
    db.add(instance)
    db.flush()
    db.refresh(instance)

    logger.info(
        "创建 instance id={} script={} name={!r}",
        instance.id,
        script.slug,
        instance.name,
    )

    # 6. 注册到调度器(若 enabled 且有 cron)
    if scheduler is not None:
        try:
            scheduler.register(instance)
        except Exception as exc:  # noqa: BLE001
            logger.error("scheduler.register 失败: {}", exc)

    return _serialize_instance_for_detail(instance, script, cipher)


# ============================================================
# 详情
# ============================================================
def get_instance(db: Session, instance_id: int) -> Instance:
    """取实例 ORM 对象;不存在抛 :class:`InstanceNotFound`。"""
    return _get_instance_or_404(db, instance_id)


def get_instance_detail(
    db: Session, instance_id: int, cipher: FernetCipher
) -> dict[str, Any]:
    """详情(含解密 + 脱敏的 config)。"""
    instance = _get_instance_or_404(db, instance_id)
    script = db.get(Script, instance.script_id)
    if script is None:
        raise InstanceNotFound(
            f"实例 {instance_id} 关联脚本不存在",
            details={"instance_id": instance_id},
        )
    return _serialize_instance_for_detail(instance, script, cipher)


# ============================================================
# 更新
# ============================================================
def update_instance(
    db: Session,
    instance_id: int,
    payload: Any,
    cipher: FernetCipher,
    scheduler: "SchedulerService | None" = None,
) -> dict[str, Any]:
    """PATCH — 部分字段更新。

    关键(设计稿 § 5.2):
    - secret 字段在 ``payload.config`` 中未提交 / None / 空串 → 保留原值
    - 其余 config 字段以新值覆盖
    - cron / enabled 变化时调用 ``scheduler.reschedule``
    """
    instance = _get_instance_or_404(db, instance_id)
    script = db.get(Script, instance.script_id)
    if script is None:
        raise InstanceNotFound(
            f"实例 {instance_id} 关联脚本不存在",
            details={"instance_id": instance_id},
        )

    fields = _load_fields(script)

    cron_changed = False
    enabled_changed = False

    if payload.name is not None:
        instance.name = payload.name
    if payload.description is not None:
        instance.description = payload.description
    if payload.cron_expr is not None:
        # 允许空字符串清空(走 default_cron)
        new_cron = payload.cron_expr.strip() or None
        # audit High #10:写库前 cron 合法性预校验,而不是 reschedule 时才崩
        if new_cron is not None:
            _validate_cron_expr(new_cron)
        if new_cron != instance.cron_expr:
            cron_changed = True
        instance.cron_expr = new_cron
    if payload.timeout_sec is not None:
        instance.timeout_sec = payload.timeout_sec
    if payload.max_retries is not None:
        instance.max_retries = payload.max_retries
    if payload.retry_interval_sec is not None:
        instance.retry_interval_sec = payload.retry_interval_sec
    if payload.enabled is not None:
        if payload.enabled != instance.enabled:
            enabled_changed = True
        instance.enabled = payload.enabled

    # config 合并
    if payload.config is not None:
        # 解旧
        if instance.config_blob:
            try:
                old_config = cipher.decrypt_dict(instance.config_blob)
            except Exception as exc:  # noqa: BLE001
                logger.error("config 解密失败 instance={}: {}", instance.id, exc)
                old_config = {}
        else:
            old_config = {}

        # secret 字段未提交 → 保留旧值
        merged = merge_secrets(old_config, payload.config, fields)

        # 校验(merged 是完整的)
        cleaned = validate_config(merged, fields)
        instance.config_blob = (
            cipher.encrypt_dict(cleaned) if cleaned else ""
        )

    db.flush()
    db.refresh(instance)

    # 调度器同步
    if scheduler is not None and (cron_changed or enabled_changed):
        try:
            scheduler.reschedule(instance)
        except Exception as exc:  # noqa: BLE001
            logger.error("scheduler.reschedule 失败: {}", exc)

    return _serialize_instance_for_detail(instance, script, cipher)


# ============================================================
# 删除
# ============================================================
def delete_instance(
    db: Session,
    instance_id: int,
    scheduler: "SchedulerService | None" = None,
) -> None:
    """删除实例 + 级联删 runs + 从调度器摘除。"""
    instance = _get_instance_or_404(db, instance_id)

    # 先解 last_run_id 防 FK 自指环导致级联失败
    instance.last_run_id = None
    db.flush()

    if scheduler is not None:
        try:
            scheduler.unregister(instance_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("scheduler.unregister 失败: {}", exc)

    db.delete(instance)
    db.flush()
    logger.info("删除 instance id={}", instance_id)


# ============================================================
# 启用 / 禁用
# ============================================================
def enable_instance(
    db: Session,
    instance_id: int,
    scheduler: "SchedulerService | None" = None,
    cipher: FernetCipher | None = None,
) -> dict[str, Any]:
    instance = _get_instance_or_404(db, instance_id)
    if not instance.enabled:
        instance.enabled = True
        db.flush()
        logger.info("启用 instance id={}", instance_id)
    if scheduler is not None:
        try:
            scheduler.register(instance)
        except Exception as exc:  # noqa: BLE001
            logger.error("scheduler.register 失败: {}", exc)
    script = db.get(Script, instance.script_id)
    cipher = cipher or get_cipher()
    return _serialize_instance_for_detail(instance, script, cipher)


def disable_instance(
    db: Session,
    instance_id: int,
    scheduler: "SchedulerService | None" = None,
    cipher: FernetCipher | None = None,
) -> dict[str, Any]:
    instance = _get_instance_or_404(db, instance_id)
    if instance.enabled:
        instance.enabled = False
        db.flush()
        logger.info("禁用 instance id={}", instance_id)
    if scheduler is not None:
        try:
            scheduler.unregister(instance_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("scheduler.unregister 失败: {}", exc)
    script = db.get(Script, instance.script_id)
    cipher = cipher or get_cipher()
    return _serialize_instance_for_detail(instance, script, cipher)


# ============================================================
# 暂停 / 恢复
# ============================================================
def pause_instance(
    db: Session,
    instance_id: int,
    until: datetime,
    scheduler: "SchedulerService | None" = None,
    cipher: FernetCipher | None = None,
) -> dict[str, Any]:
    instance = _get_instance_or_404(db, instance_id)

    now = _utcnow()
    if until.tzinfo is None:
        until = until.replace(tzinfo=timezone.utc)
    if until <= now:
        raise ValidationError(
            "pause until 必须是未来时间",
            details={"until": until.isoformat()},
        )
    instance.paused_until = until
    db.flush()
    logger.info("暂停 instance id={} until={}", instance_id, until)

    if scheduler is not None:
        try:
            scheduler.pause(instance_id, until)
        except Exception as exc:  # noqa: BLE001
            logger.warning("scheduler.pause 失败: {}", exc)

    script = db.get(Script, instance.script_id)
    cipher = cipher or get_cipher()
    return _serialize_instance_for_detail(instance, script, cipher)


def resume_instance(
    db: Session,
    instance_id: int,
    scheduler: "SchedulerService | None" = None,
    cipher: FernetCipher | None = None,
) -> dict[str, Any]:
    instance = _get_instance_or_404(db, instance_id)
    instance.paused_until = None
    db.flush()
    logger.info("恢复 instance id={}", instance_id)

    if scheduler is not None:
        try:
            scheduler.resume(instance_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("scheduler.resume 失败: {}", exc)

    script = db.get(Script, instance.script_id)
    cipher = cipher or get_cipher()
    return _serialize_instance_for_detail(instance, script, cipher)


# ============================================================
# 立即触发 + 试运行
# ============================================================
def trigger_instance(
    db: Session,
    instance_id: int,
    *,
    scheduler: "SchedulerService",
    trigger_user_id: int | None = None,
    trigger_type: str = "manual",
) -> int:
    """立即触发一次执行,返回新建的 ``run_id``。

    流程:
    1. 校验实例存在 + 未禁用
    2. 在 DB 内先创建 pending run(让前端立刻拿到 run_id)
    3. 提交事务
    4. 用 ``scheduler.trigger_now(..., pre_created_run_id=...)`` 异步启执行
    """
    instance = _get_instance_or_404(db, instance_id)
    script = db.get(Script, instance.script_id)
    if script is None:
        raise InstanceNotFound(
            f"实例 {instance_id} 关联脚本不存在",
            details={"instance_id": instance_id},
        )

    now = _utcnow()
    run = Run(
        instance_id=instance_id,
        script_slug=script.slug,
        trigger_type=trigger_type,
        trigger_user_id=trigger_user_id,
        status="pending",
        started_at=now,
    )
    db.add(run)
    db.flush()
    db.refresh(run)
    run_id = run.id

    # 提交事务,确保子任务能查到 run
    db.commit()

    # 异步启动执行(fire-and-forget)
    try:
        scheduler.trigger_now(
            instance_id,
            trigger_type=trigger_type,
            trigger_user_id=trigger_user_id,
            pre_created_run_id=run_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("scheduler.trigger_now 失败: {}", exc)
        raise

    logger.info(
        "已触发 instance.{} trigger={} run_id={}",
        instance_id,
        trigger_type,
        run_id,
    )
    return run_id


async def test_instance(
    db: Session,
    instance_id: int,
    cipher: FernetCipher,
) -> dict[str, Any]:
    """试运行 — 不写 runs,不发通知。

    设计稿 § 2.3:**不可与 run 并发跑同一 instance**。这里用乐观策略 —
    若发现 instance 有 running / pending run,抛 ConcurrentRunConflict。
    """
    _ = cipher  # 当前签名保留但未直接用(decrypt 在 executor 内做)
    instance = _get_instance_or_404(db, instance_id)
    # 并发检查
    in_progress = db.scalars(
        select(Run).where(
            Run.instance_id == instance.id,
            Run.status.in_(["pending", "running"]),
        )
    ).first()
    if in_progress is not None:
        raise ConcurrentRunConflict(
            "该实例已有任务正在执行,无法同时 test",
            details={
                "instance_id": instance_id,
                "blocking_run_id": in_progress.id,
            },
        )

    # 跳出 session 跑 — executor 内自己开 session
    try:
        result = await run_instance_test(instance_id)
    except Exception as exc:  # noqa: BLE001
        raise ValidationError(
            f"试运行失败: {type(exc).__name__}: {exc}",
            details={"instance_id": instance_id},
        )

    return {
        "success": result["status"] == "success",
        "status": result["status"],
        "exit_code": result["exit_code"],
        "duration_ms": result["duration_ms"],
        "result_message": result["result_message"],
        "result_data": result["result_data"],
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "stdout_truncated": result["stdout_truncated"],
        "stderr_truncated": result["stderr_truncated"],
    }
