"""通知 service — 渠道 CRUD / 规则 CRUD / 模板预览 / test_send。

实现见 `进度/设计/后端架构.md` § 2.5 + § 1.5 / § 1.6。

公开函数(渠道)
----------------
- ``list_channels(db) -> list[NotificationChannel]``
- ``get_channel(db, id) -> NotificationChannel``
- ``create_channel(db, *, name, type, apprise_url, description, enabled, cipher) -> NotificationChannel``
- ``update_channel(db, id, *, patch, cipher) -> NotificationChannel``
- ``delete_channel(db, id) -> None``
- ``async test_channel(db, id, *, title, body, cipher, pool) -> tuple[bool, float, str | None]``

公开函数(规则)
----------------
- ``list_rules(db, *, scope, script_id, instance_id, channel_id) -> list[NotificationRule]``
- ``get_rule(db, id) -> NotificationRule``
- ``create_rule(db, *, payload) -> NotificationRule``
- ``update_rule(db, id, *, patch) -> NotificationRule``
- ``delete_rule(db, id) -> None``
- ``preview_rule(db, id) -> tuple[str, str]``

错误统一抛 ``app.core.exceptions.*``。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import (
    ChannelNotFound,
    DuplicateName,
    InstanceNotFound,
    RuleNotFound,
    ScriptNotFound,
    ValidationError,
)
from app.db.models.instance import Instance
from app.db.models.notification import NotificationChannel, NotificationRule
from app.db.models.script import Script
from app.notifications import apprise_client as _apprise_mod
from app.notifications import templates as _templates_mod
from app.schemas.notification import (
    ChannelPatchRequest,
    RuleCreateRequest,
    RulePatchRequest,
)

if TYPE_CHECKING:
    from app.core.crypto import FernetCipher


# ============================================================
# 渠道
# ============================================================
def list_channels(db: Session) -> list[NotificationChannel]:
    """列表(按 name 升序)。"""
    stmt = select(NotificationChannel).order_by(NotificationChannel.name.asc())
    return list(db.scalars(stmt).all())


def get_channel(db: Session, channel_id: int) -> NotificationChannel:
    """按 id 取;不存在抛 :class:`ChannelNotFound`。"""
    ch = db.get(NotificationChannel, channel_id)
    if ch is None:
        raise ChannelNotFound(
            f"通知渠道不存在: {channel_id}",
            details={"channel_id": channel_id},
        )
    return ch


def _ensure_unique_name(
    db: Session,
    name: str,
    *,
    exclude_id: int | None = None,
) -> None:
    """确保 name 在 channels 表内 unique;冲突抛 DuplicateName。"""
    stmt = select(NotificationChannel.id).where(NotificationChannel.name == name)
    if exclude_id is not None:
        stmt = stmt.where(NotificationChannel.id != exclude_id)
    row = db.scalars(stmt).first()
    if row is not None:
        raise DuplicateName(
            f"渠道名称已存在: {name!r}",
            details={"field": "name", "value": name},
        )


def create_channel(
    db: Session,
    *,
    name: str,
    type: str,  # noqa: A002 — 与 schema 字段同名
    apprise_url: str,
    description: str | None,
    enabled: bool,
    cipher: FernetCipher,
) -> NotificationChannel:
    """新建渠道;``apprise_url`` 加密落库。"""
    _ensure_unique_name(db, name)

    blob = cipher.encrypt(apprise_url)
    ch = NotificationChannel(
        name=name,
        type=type,
        apprise_url_blob=blob,
        description=description,
        enabled=enabled,
    )
    db.add(ch)
    db.flush()
    logger.info("新建通知渠道 channel_id={} name={!r} type={}", ch.id, name, type)
    return ch


def update_channel(
    db: Session,
    channel_id: int,
    *,
    patch: ChannelPatchRequest,
    cipher: FernetCipher,
) -> NotificationChannel:
    """更新渠道;``apprise_url`` 未传 = 保留原值。"""
    ch = get_channel(db, channel_id)

    if patch.name is not None and patch.name != ch.name:
        _ensure_unique_name(db, patch.name, exclude_id=ch.id)
        ch.name = patch.name
    if patch.type is not None:
        ch.type = patch.type
    if patch.description is not None:
        ch.description = patch.description
    if patch.enabled is not None:
        ch.enabled = patch.enabled
    if patch.apprise_url is not None:
        ch.apprise_url_blob = cipher.encrypt(patch.apprise_url)

    db.flush()

    # 渠道变更 → 同步清掉 apprise 池缓存(下次 send 会用新 URL 重建)
    # 直接操作内部 dict(GIL 保护);避免依赖 event loop 状态
    pool = _apprise_mod.get_pool()
    pool._cache.pop(channel_id, None)  # noqa: SLF001 — 已知内部缓存结构

    logger.info("更新通知渠道 channel_id={} name={!r}", ch.id, ch.name)
    return ch


def delete_channel(db: Session, channel_id: int) -> None:
    """删除;级联删其所有 rules(由 FK 配置保证)。"""
    ch = get_channel(db, channel_id)
    db.delete(ch)
    db.flush()
    logger.info("删除通知渠道 channel_id={}", channel_id)


async def test_channel(
    db: Session,
    channel_id: int,
    *,
    title: str | None,
    body: str | None,
    cipher: FernetCipher,
    pool: _apprise_mod.AppriseClientPool,
) -> tuple[bool, float, str | None]:
    """立即发送测试消息,返回 ``(ok, latency_ms, error)``。

    成功/失败都更新 ``last_test_at`` / ``last_test_ok``;调用方 commit。
    """
    ch = get_channel(db, channel_id)
    if not ch.enabled:
        # 测试时允许 disabled 渠道直接试发(用户调试用),只记录但不阻止
        logger.info("测试已禁用的渠道 channel_id={}(允许试发)", channel_id)

    try:
        apprise_url = cipher.decrypt(ch.apprise_url_blob)
    except Exception as exc:  # noqa: BLE001
        from datetime import datetime, timezone  # noqa: PLC0415

        ch.last_test_at = datetime.now(timezone.utc)
        ch.last_test_ok = False
        db.flush()
        return False, 0.0, f"解密 apprise_url 失败: {exc}"

    real_title = title or f"[测试] 通知渠道 {ch.name}"
    real_body = body or (
        "这是一条来自签到管家的测试通知。\n\n"
        f"- 渠道名称: {ch.name}\n"
        f"- 渠道类型: {ch.type}\n"
        f"- 渠道 ID: {ch.id}\n\n"
        "如果你看到这条消息,说明通知通道工作正常。"
    )

    ok, latency_ms, err = await pool.send(
        channel_id=ch.id,
        channel_type=ch.type,
        apprise_url=apprise_url,
        title=real_title,
        body=real_body,
        body_format="markdown",
    )

    from datetime import datetime, timezone  # noqa: PLC0415

    ch.last_test_at = datetime.now(timezone.utc)
    ch.last_test_ok = bool(ok)
    db.flush()
    return ok, latency_ms, err


# ============================================================
# 规则
# ============================================================
def list_rules(
    db: Session,
    *,
    scope: str | None = None,
    script_id: int | None = None,
    instance_id: int | None = None,
    channel_id: int | None = None,
) -> list[NotificationRule]:
    """规则列表 + 多维筛选(AND)。"""
    stmt = select(NotificationRule)
    if scope:
        stmt = stmt.where(NotificationRule.scope == scope)
    if script_id is not None:
        stmt = stmt.where(NotificationRule.script_id == script_id)
    if instance_id is not None:
        stmt = stmt.where(NotificationRule.instance_id == instance_id)
    if channel_id is not None:
        stmt = stmt.where(NotificationRule.channel_id == channel_id)
    stmt = stmt.order_by(NotificationRule.id.asc())
    return list(db.scalars(stmt).all())


def get_rule(db: Session, rule_id: int) -> NotificationRule:
    rule = db.get(NotificationRule, rule_id)
    if rule is None:
        raise RuleNotFound(
            f"通知规则不存在: {rule_id}",
            details={"rule_id": rule_id},
        )
    return rule


def _ensure_channel_exists(db: Session, channel_id: int) -> None:
    if db.get(NotificationChannel, channel_id) is None:
        raise ChannelNotFound(
            f"通知渠道不存在: {channel_id}",
            details={"channel_id": channel_id},
        )


def _validate_scope_targets(
    db: Session,
    *,
    scope: str,
    script_id: int | None,
    instance_id: int | None,
) -> None:
    """校验 scope 与 script_id/instance_id 是否一致(含 instance.script_id 匹配)。

    会做 DB 查询,确保 FK 目标存在。
    """
    if scope == "global":
        if script_id is not None or instance_id is not None:
            raise ValidationError(
                "scope=global 时 script_id / instance_id 必须为空",
                details={"scope": scope},
            )
        return

    if scope == "script":
        if script_id is None:
            raise ValidationError(
                "scope=script 时 script_id 必填",
                details={"scope": scope},
            )
        if instance_id is not None:
            raise ValidationError(
                "scope=script 时 instance_id 必须为空",
                details={"scope": scope},
            )
        if db.get(Script, script_id) is None:
            raise ScriptNotFound(
                f"script 不存在: {script_id}",
                details={"script_id": script_id},
            )
        return

    if scope == "instance":
        if script_id is None or instance_id is None:
            raise ValidationError(
                "scope=instance 时 script_id 和 instance_id 都必填",
                details={"scope": scope},
            )
        inst = db.get(Instance, instance_id)
        if inst is None:
            raise InstanceNotFound(
                f"instance 不存在: {instance_id}",
                details={"instance_id": instance_id},
            )
        if int(inst.script_id) != int(script_id):
            raise ValidationError(
                f"instance.script_id({inst.script_id}) 与 script_id({script_id}) 不一致",
                details={
                    "instance_id": instance_id,
                    "expected_script_id": int(inst.script_id),
                    "got_script_id": int(script_id),
                },
            )
        return

    raise ValidationError(
        f"未知 scope: {scope!r}",
        details={"scope": scope, "allowed": ["global", "script", "instance"]},
    )


def create_rule(db: Session, *, payload: RuleCreateRequest) -> NotificationRule:
    """新建规则。"""
    _ensure_channel_exists(db, payload.channel_id)
    _validate_scope_targets(
        db,
        scope=payload.scope,
        script_id=payload.script_id,
        instance_id=payload.instance_id,
    )

    rule = NotificationRule(
        name=payload.name,
        scope=payload.scope,
        script_id=payload.script_id,
        instance_id=payload.instance_id,
        event=payload.event,
        channel_id=payload.channel_id,
        template=payload.template,
        min_interval_sec=payload.min_interval_sec,
        enabled=payload.enabled,
    )
    db.add(rule)
    db.flush()
    logger.info(
        "新建通知规则 rule_id={} name={!r} scope={} event={} channel_id={}",
        rule.id,
        rule.name,
        rule.scope,
        rule.event,
        rule.channel_id,
    )
    return rule


def update_rule(
    db: Session, rule_id: int, *, patch: RulePatchRequest
) -> NotificationRule:
    """更新规则。

    若提供了 scope / script_id / instance_id 任一,会把当前值与新值合并后
    用 :func:`_validate_scope_targets` 重新校验。
    """
    rule = get_rule(db, rule_id)

    # 先合并出"updated 后的"目标 scope/script_id/instance_id 用于一致性校验
    new_scope = patch.scope if patch.scope is not None else rule.scope
    new_script_id = (
        patch.script_id if patch.script_id is not None else rule.script_id
    )
    new_instance_id = (
        patch.instance_id if patch.instance_id is not None else rule.instance_id
    )
    # 注意:patch.script_id / instance_id 都允许显式置 None?
    # Pydantic 模型里没法区分"未传"和"显式 null"——这里采用语义:patch 字段
    # 若为 None 则保留原值。要置空请配合 scope=global 调用(必然走校验)。

    # 若 scope 改变,触发完整校验
    if (
        patch.scope is not None
        or patch.script_id is not None
        or patch.instance_id is not None
    ):
        # 对 scope=global 的语义对齐:强制把 script_id / instance_id 清空
        if new_scope == "global":
            new_script_id, new_instance_id = None, None
        _validate_scope_targets(
            db,
            scope=new_scope,
            script_id=new_script_id,
            instance_id=new_instance_id,
        )
        rule.scope = new_scope
        rule.script_id = new_script_id
        rule.instance_id = new_instance_id

    if patch.name is not None:
        rule.name = patch.name
    if patch.event is not None:
        rule.event = patch.event
    if patch.channel_id is not None and patch.channel_id != rule.channel_id:
        _ensure_channel_exists(db, patch.channel_id)
        rule.channel_id = patch.channel_id
    if patch.template is not None:
        rule.template = patch.template
    if patch.min_interval_sec is not None:
        rule.min_interval_sec = patch.min_interval_sec
    if patch.enabled is not None:
        rule.enabled = patch.enabled

    db.flush()
    logger.info("更新通知规则 rule_id={}", rule.id)
    return rule


def delete_rule(db: Session, rule_id: int) -> None:
    rule = get_rule(db, rule_id)
    db.delete(rule)
    db.flush()
    logger.info("删除通知规则 rule_id={}", rule_id)


def preview_rule(db: Session, rule_id: int) -> tuple[str, str]:
    """用 sample ctx 渲染 rule 模板,返回 ``(title, body)``;不发送。"""
    rule = get_rule(db, rule_id)
    # event 选规则的具体 event;'any' → 用 failure 让 stderr 段出现
    event = rule.event
    if event == "any":
        event = "failure"
    ctx = _templates_mod.build_sample_context(event=event)
    try:
        title, body = _templates_mod.render_notification(rule.template, ctx)
    except Exception as exc:  # noqa: BLE001
        raise ValidationError(
            f"模板渲染失败: {exc}",
            details={"rule_id": rule_id, "error": str(exc)},
        ) from exc
    return title, body


# ============================================================
# 给路由层用的小工具(脱敏)
# ============================================================
def to_list_item_dict(ch: NotificationChannel) -> dict[str, Any]:
    """把 ORM 渠道转 dict(供 ChannelListItem.model_validate)。

    包含 ``apprise_url_masked``;不暴露 ``apprise_url_blob``。
    """
    return {
        "id": ch.id,
        "name": ch.name,
        "type": ch.type,
        "apprise_url_masked": _apprise_mod.mask_apprise_url(
            _try_decrypt_for_mask(ch.apprise_url_blob)
        ),
        "description": ch.description,
        "enabled": ch.enabled,
        "last_test_at": ch.last_test_at,
        "last_test_ok": ch.last_test_ok,
        "created_at": ch.created_at,
        "updated_at": ch.updated_at,
    }


def _try_decrypt_for_mask(blob: str) -> str:
    """解密 blob 仅为提取 scheme 做脱敏;失败返回 ``""``。"""
    try:
        from app.core.crypto import get_cipher  # noqa: PLC0415

        return get_cipher().decrypt(blob)
    except Exception:  # noqa: BLE001
        return ""
