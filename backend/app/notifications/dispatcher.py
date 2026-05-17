"""通知事件分发 — 给定 run + event,匹配规则,渲染模板,调 apprise。

实现见 `进度/设计/后端架构.md` § 1.6 末段 + § 2.5。

公开
----
- ``async dispatch_run_event(db, run, event, *, cipher=None, pool=None)`` —
  外部调用入口(executor 在 run 完成后调用)
- ``match_rules(db, *, event, script_id, instance_id) -> list[NotificationRule]`` —
  按 scope 优先级去重后的命中规则列表

实现要点
--------
- 匹配 rules:scope=global / scope=script(且 script_id 匹配)/
  scope=instance(且 instance_id 匹配);event 命中 "any" 或具体事件
- 同 channel 命中多 rule → 取 scope 更具体的(instance > script > global)
- ``min_interval_sec`` 节流:用 ``last_fired_at`` 比对当前时间
- 单 rule 失败不阻塞其它 rule;**整体 try 包住**,异常只写日志不抛
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from loguru import logger
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models.notification import NotificationChannel, NotificationRule
from app.notifications import apprise_client as _apprise_mod
from app.notifications import templates as _templates_mod

if TYPE_CHECKING:
    from app.core.crypto import FernetCipher


# scope 优先级(数字越大越具体)
_SCOPE_PRIORITY: dict[str, int] = {"global": 0, "script": 1, "instance": 2}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ============================================================
# 匹配
# ============================================================
def match_rules(
    db: Session,
    *,
    event: str,
    script_id: int | None,
    instance_id: int | None,
) -> list[NotificationRule]:
    """返回命中且 enabled 的规则,按"同渠道取最具体" 去重后的列表。

    命中条件:
    - rule.enabled = true
    - rule.event = event 或 rule.event = 'any'
    - scope=global → 总命中
      scope=script → script_id 必须等于参数 script_id
      scope=instance → instance_id 必须等于参数 instance_id
    """
    if event not in ("success", "failure", "error", "timeout"):
        # 'any' 不应被 dispatcher 传入(它是规则配置的 wildcard)
        logger.debug("dispatch 收到未知 event={},不处理", event)
        return []

    # 一次查询拉所有可能命中的规则,然后内存里筛/去重
    # 这样比一条条 SQL 调用更省 DB 时间
    scope_filter = NotificationRule.scope.in_(
        ["global", "script", "instance"]
    )
    event_filter = or_(
        NotificationRule.event == event,
        NotificationRule.event == "any",
    )

    stmt = select(NotificationRule).where(
        NotificationRule.enabled.is_(True),
        scope_filter,
        event_filter,
    )
    all_rules = list(db.scalars(stmt).all())

    matched: list[NotificationRule] = []
    for rule in all_rules:
        if rule.scope == "global":
            matched.append(rule)
        elif rule.scope == "script":
            if script_id is not None and rule.script_id == script_id:
                matched.append(rule)
        elif rule.scope == "instance":
            if instance_id is not None and rule.instance_id == instance_id:
                matched.append(rule)
        else:  # pragma: no cover
            continue

    if not matched:
        return []

    # 同 channel 取 scope 优先级最高的(instance > script > global);
    # 同优先级取 id 较大者(便于"用户最后创建的覆盖")
    best_per_channel: dict[int, NotificationRule] = {}
    for r in matched:
        existing = best_per_channel.get(r.channel_id)
        if existing is None:
            best_per_channel[r.channel_id] = r
            continue
        cur_p = _SCOPE_PRIORITY.get(r.scope, 0)
        ex_p = _SCOPE_PRIORITY.get(existing.scope, 0)
        if cur_p > ex_p or (cur_p == ex_p and r.id > existing.id):
            best_per_channel[r.channel_id] = r

    # 返回 list,保证遍历顺序稳定(按 channel_id 升序)
    return [best_per_channel[k] for k in sorted(best_per_channel.keys())]


# ============================================================
# 节流
# ============================================================
def _is_throttled(rule: NotificationRule, now: datetime) -> bool:
    """检查 rule 是否在 ``min_interval_sec`` 节流期内。"""
    if rule.min_interval_sec is None or rule.min_interval_sec <= 0:
        return False
    last = rule.last_fired_at
    if last is None:
        return False
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return (now - last) < timedelta(seconds=int(rule.min_interval_sec))


# ============================================================
# Dispatch 入口
# ============================================================
async def dispatch_run_event(
    db: Session,
    run: Any,
    event: str,
    *,
    cipher: FernetCipher | None = None,
    pool: _apprise_mod.AppriseClientPool | None = None,
) -> int:
    """对一个完成的 run 触发匹配的所有通知。

    参数
    ----
    - ``db``:SQLAlchemy session(由调用方提供,本函数 flush 不 commit)
    - ``run``:已完成的 :class:`app.db.models.run.Run`(或类似 ORM)
    - ``event``:``success`` / ``failure`` / ``error`` / ``timeout``
    - ``cipher``:Fernet 解密器(默认从 ``app.core.crypto.get_cipher()`` 取)
    - ``pool``:apprise 实例池(默认从 ``apprise_client.get_pool()`` 取)

    返回
    ----
    int — 实际成功送达的渠道数(失败/节流跳过的不计)。

    说明
    ----
    - 单条 rule / channel 失败**不影响**其它通道
    - 节流跳过的 rule 不更新 ``last_fired_at``(否则永远节流)
    - 发送结束更新 ``rule.last_fired_at`` 与 ``channel.last_test_*`` 不动
    - 整个流程被 ``try/except`` 兜住,确保 executor 不被通知失败连累
    """
    if cipher is None:
        # 局部 import 避免循环
        from app.core.crypto import get_cipher  # noqa: PLC0415

        cipher = get_cipher()
    if pool is None:
        pool = _apprise_mod.get_pool()

    try:
        script_id = _extract_script_id(db, run)
        instance_id = getattr(run, "instance_id", None)
        rules = match_rules(
            db,
            event=event,
            script_id=script_id,
            instance_id=instance_id,
        )
        if not rules:
            return 0

        # 一次性加载所有相关 channel(避免逐 rule lazy-load)
        channel_ids = [r.channel_id for r in rules]
        channels: dict[int, NotificationChannel] = {
            c.id: c
            for c in db.scalars(
                select(NotificationChannel).where(
                    NotificationChannel.id.in_(channel_ids)
                )
            ).all()
        }

        # 渲染上下文 — 需要 script / instance ORM 完整对象
        script = _load_script(db, script_id)
        instance = _load_instance(db, instance_id)

        ctx = _templates_mod.build_context(
            run=run,
            instance=instance,
            script=script,
            event=event,
        )

        success_count = 0
        now = _utcnow()
        for rule in rules:
            channel = channels.get(rule.channel_id)
            if channel is None or not channel.enabled:
                logger.debug(
                    "渠道不存在或已禁用,跳过 rule_id={} channel_id={}",
                    rule.id,
                    rule.channel_id,
                )
                continue
            if _is_throttled(rule, now):
                logger.info(
                    "rule 节流跳过 rule_id={} min_interval_sec={}",
                    rule.id,
                    rule.min_interval_sec,
                )
                continue

            # 解密 apprise_url
            try:
                apprise_url = cipher.decrypt(channel.apprise_url_blob)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "解密 channel.apprise_url 失败 channel_id={} err={}",
                    channel.id,
                    exc,
                )
                continue

            # 渲染模板
            try:
                title, body = _templates_mod.render_notification(
                    rule.template, ctx
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "渲染通知模板失败 rule_id={} err={}", rule.id, exc
                )
                continue

            ok, latency_ms, err = await pool.send(
                channel_id=channel.id,
                channel_type=channel.type,
                apprise_url=apprise_url,
                title=title,
                body=body,
                body_format="markdown",
            )
            if ok:
                success_count += 1
                rule.last_fired_at = now
            else:
                logger.warning(
                    "rule 发送失败 rule_id={} channel_id={} latency_ms={:.0f} err={}",
                    rule.id,
                    channel.id,
                    latency_ms,
                    err,
                )

        # flush rule.last_fired_at 更新
        if success_count > 0:
            db.flush()

        return success_count

    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "dispatch_run_event 整体异常 run_id={} event={} err={}",
            getattr(run, "id", None),
            event,
            exc,
        )
        return 0


# ============================================================
# 内部:从 run 找 script_id / 加载 ORM
# ============================================================
def _extract_script_id(db: Session, run: Any) -> int | None:
    """从 run 反推 script_id。

    Run 表只有 ``script_slug``,所以需要 join 一次 scripts 表。
    若 instance 还在内存且已 loaded,可以直接走 instance.script_id 省一次查询。
    """
    inst = getattr(run, "instance", None)
    if inst is not None and getattr(inst, "script_id", None):
        return int(inst.script_id)

    slug = getattr(run, "script_slug", None)
    if not slug:
        return None

    # 局部 import 防循环
    from app.db.models.script import Script  # noqa: PLC0415

    row = db.scalars(select(Script.id).where(Script.slug == slug)).one_or_none()
    return int(row) if row is not None else None


def _load_script(db: Session, script_id: int | None) -> Any:
    if script_id is None:
        return None
    from app.db.models.script import Script  # noqa: PLC0415

    return db.get(Script, script_id)


def _load_instance(db: Session, instance_id: int | None) -> Any:
    if instance_id is None:
        return None
    from app.db.models.instance import Instance  # noqa: PLC0415

    return db.get(Instance, instance_id)
