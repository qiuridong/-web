"""Node 节点 service — CRUD + token 生成/校验 + 心跳 + heartbeat。

MVP-1 远程 agent 架构,设计稿:`进度/设计/远程VPS脚本执行调研.md` § 5 / § 7。

公开函数
--------
- :func:`list_nodes` 全部节点
- :func:`create_node` 同时生成明文 token,bcrypt 存表,**返回明文给调用方一次**
- :func:`get_node` / :func:`get_node_by_id` / :func:`get_node_by_slug`
- :func:`update_node` 改 name/description/enabled
- :func:`delete_node` is_local=1 不可删;有关联 instance 时阻止
- :func:`regenerate_token` 返回新明文 token,旧 token 立即失效
- :func:`authenticate_agent` 给 middleware 用:Bearer token → Node | None;
  顺便更新 ``last_seen_at``
- :func:`update_heartbeat` agent heartbeat 时调,更新 version + metadata
- :func:`ensure_local_node` 启动时调,确保 id=1 / slug='local' 存在(idempotent)

设计要点
--------
- token 格式:``sa_<32 url-safe chars>``,256 bits 熵
- 存表用 bcrypt(token);校验时全表扫(N < 10,可接受)
- agent 端 token 一次性返回明文 → 前端弹窗显示 → 关闭后 DB 只剩 hash
- last_seen_at 用 UTC,UI 端按节点 enabled + last_seen_at > 60s 判离线
"""
from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionError as AppPermissionError,
    ValidationError,
)
from app.core.security import hash_password, verify_password
from app.db.models.instance import Instance
from app.db.models.node import Node


# ============================================================
# 常量
# ============================================================
#: token 前缀,便于人眼识别(grep / 截图脱敏)
TOKEN_PREFIX = "sa_"

#: token 随机部分长度(url-safe);最终长度 = 3 + 43 ≈ 46
TOKEN_RANDOM_BYTES = 32


# ============================================================
# 辅助
# ============================================================
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _generate_token() -> str:
    """生成新 agent token,明文形态。"""
    random_part = secrets.token_urlsafe(TOKEN_RANDOM_BYTES)
    return f"{TOKEN_PREFIX}{random_part}"


def _hash_token(token: str) -> str:
    """bcrypt 哈希 token,与密码同处理(共用 bcrypt.gensalt)。"""
    return hash_password(token)


def _verify_token(token: str, hashed: str) -> bool:
    """bcrypt 校验 token 是否匹配 hash。"""
    return verify_password(token, hashed)


def _validate_slug(slug: str) -> None:
    """slug 校验:[a-z0-9][a-z0-9-]{0,62}。"""
    if not slug:
        raise ValidationError("slug 不能为空")
    if len(slug) > 64:
        raise ValidationError(f"slug 过长(>64): {slug!r}")
    import re

    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", slug):
        raise ValidationError(
            "slug 必须以小写字母/数字开头,只含小写字母/数字/连字符",
            details={"slug": slug},
        )


# ============================================================
# 列表 / 查询
# ============================================================
def list_nodes(db: Session) -> list[Node]:
    """全部节点(按 id 升序;local 在最前)。"""
    return list(db.scalars(select(Node).order_by(Node.id)).all())


def get_node_by_id(db: Session, node_id: int) -> Node:
    node = db.get(Node, node_id)
    if node is None:
        raise NotFoundError(
            f"未找到节点 id={node_id}",
            details={"node_id": node_id},
        )
    return node


def get_node_by_slug(db: Session, slug: str) -> Node | None:
    return db.scalars(select(Node).where(Node.slug == slug)).one_or_none()


# ============================================================
# 创建
# ============================================================
def create_node(
    db: Session,
    *,
    slug: str,
    name: str | None = None,
    description: str | None = None,
) -> tuple[Node, str]:
    """创建一个新节点(远程 agent),返回 (Node, 明文 token)。

    明文 token 只在此处返回**一次**;前端必须立即保存,关闭弹窗后无法再取。

    :raises ConflictError: slug 重复
    :raises ValidationError: slug 不合法
    """
    _validate_slug(slug)

    # 重名检查
    existing = get_node_by_slug(db, slug)
    if existing is not None:
        raise ConflictError(
            f"slug 已存在: {slug!r}",
            details={"slug": slug, "existing_id": existing.id},
        )

    # 生成 token
    token = _generate_token()
    token_hash = _hash_token(token)

    node = Node(
        slug=slug,
        name=name or slug,
        description=description,
        is_local=False,
        auth_token_hash=token_hash,
        enabled=True,
    )
    db.add(node)
    db.flush()
    db.refresh(node)
    logger.info("创建节点 id={} slug={} name={!r}", node.id, slug, node.name)
    return node, token


# ============================================================
# 更新
# ============================================================
def update_node(
    db: Session,
    node_id: int,
    *,
    name: str | None = None,
    description: str | None = None,
    enabled: bool | None = None,
) -> Node:
    """PATCH;只更新提交的字段(None = 不动)。

    is_local 节点的 enabled 不允许改为 False(主面板必须能跑本地实例)。
    """
    node = get_node_by_id(db, node_id)
    if name is not None:
        node.name = name
    if description is not None:
        node.description = description
    if enabled is not None:
        if node.is_local and not enabled:
            raise AppPermissionError(
                "本地节点不可禁用",
                details={"node_id": node_id, "is_local": True},
            )
        node.enabled = enabled
    db.flush()
    db.refresh(node)
    logger.info("更新节点 id={} name={!r} enabled={}", node_id, node.name, node.enabled)
    return node


# ============================================================
# 删除
# ============================================================
def delete_node(db: Session, node_id: int) -> None:
    """删除节点。

    限制:
    - is_local=1 节点不可删
    - 有关联 instance 时阻止(返 409,提示用户先把 instance 改成别的节点)
    """
    node = get_node_by_id(db, node_id)
    if node.is_local:
        raise AppPermissionError(
            "本地节点不可删除",
            details={"node_id": node_id, "slug": node.slug},
        )
    # 检查是否还有 instance 关联
    instance_count = int(
        db.execute(
            select(func.count())
            .select_from(Instance)
            .where(Instance.node_id == node_id)
        ).scalar_one()
    )
    if instance_count > 0:
        raise ConflictError(
            f"该节点仍有 {instance_count} 个实例关联,请先迁移到其它节点",
            details={"node_id": node_id, "instance_count": instance_count},
        )
    db.delete(node)
    db.flush()
    logger.info("删除节点 id={} slug={}", node_id, node.slug)


# ============================================================
# token 重新生成
# ============================================================
def regenerate_token(db: Session, node_id: int) -> str:
    """生成新 token 替换旧 token,旧 token 立即失效。返回明文。

    用途:agent token 泄露 / 节点重装 时单条 rotate。
    """
    node = get_node_by_id(db, node_id)
    if node.is_local:
        raise AppPermissionError(
            "本地节点无 token",
            details={"node_id": node_id, "is_local": True},
        )
    token = _generate_token()
    node.auth_token_hash = _hash_token(token)
    db.flush()
    logger.info("重新生成节点 token id={} slug={}", node_id, node.slug)
    return token


# ============================================================
# Agent 鉴权(给 middleware 用)
# ============================================================
def authenticate_agent(db: Session, token: str | None) -> Node | None:
    """Bearer token → Node。

    校验流程:
    1. token 形态正确(以 ``sa_`` 开头)
    2. 全表扫所有 ``enabled=True AND is_local=False`` 的节点,bcrypt 校验
    3. 命中后更新 ``last_seen_at`` 并返回 Node;未命中返 None

    :returns: 成功 → Node 对象;失败 → None
    """
    if not token:
        return None
    if not token.startswith(TOKEN_PREFIX):
        return None
    # 拿出所有候选节点(无 token 的 local 节点排除)
    candidates = list(
        db.scalars(
            select(Node).where(
                Node.is_local.is_(False),
                Node.enabled.is_(True),
                Node.auth_token_hash.is_not(None),
            )
        ).all()
    )
    for node in candidates:
        if _verify_token(token, node.auth_token_hash or ""):
            # 命中 — last_seen_at 由 update_heartbeat 专责更新(30s 一次)
            # 这里不写 DB 避免与并发请求竞争 SQLite writer lock
            # (poll + heartbeat 同时到达时,authenticate_agent 双重 write 必撞 lock)
            return node
    return None


# ============================================================
# Heartbeat / metadata
# ============================================================
def update_heartbeat(
    db: Session,
    node_id: int,
    *,
    version: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Node:
    """heartbeat 入口:更新 last_seen_at + 可选 version + metadata。"""
    node = db.get(Node, node_id)
    if node is None:
        raise NotFoundError(
            f"未找到节点 id={node_id}",
            details={"node_id": node_id},
        )
    node.last_seen_at = _utcnow()
    if version is not None:
        node.version = version[:32]
    if metadata is not None:
        # 合并到现有 metadata_json,而不是完全替换 — 让 agent 可以渐进上报
        try:
            existing = (
                json.loads(node.metadata_json) if node.metadata_json else {}
            )
            if not isinstance(existing, dict):
                existing = {}
        except json.JSONDecodeError:
            existing = {}
        existing.update(metadata)
        node.metadata_json = json.dumps(existing, ensure_ascii=False)
    db.flush()
    return node


# ============================================================
# ensure_local_node:启动时调,idempotent
# ============================================================
def ensure_local_node(db: Session) -> Node:
    """启动时调,确保本地节点(id=1, slug='local', is_local=1)存在。

    alembic 0002 迁移已 INSERT 了一条,但若有人手动删了 DB 重建则此函数兜底。
    """
    node = db.get(Node, 1)
    if node is not None:
        return node
    # 没有 — 也许是迁移没跑或 user 手动删了;补一条
    logger.warning("本地节点 id=1 缺失,自动补全")
    node = Node(
        id=1,
        slug="local",
        name="本地节点",
        description="主面板自身,执行所有未指定远程节点的实例",
        is_local=True,
        enabled=True,
    )
    db.add(node)
    db.flush()
    db.refresh(node)
    return node


# ============================================================
# metadata 反序列化辅助(给 API 响应用)
# ============================================================
def node_metadata_dict(node: Node) -> dict[str, Any]:
    """metadata_json → dict;非合法 JSON 返回 {}。"""
    if not node.metadata_json:
        return {}
    try:
        d = json.loads(node.metadata_json)
        if isinstance(d, dict):
            return d
    except json.JSONDecodeError:
        pass
    return {}


def is_node_online(node: Node, threshold_seconds: int = 60) -> bool:
    """判定节点是否"在线" — last_seen_at 距今 < threshold_seconds。

    本地节点(is_local)永远算在线。
    enabled=False 节点永远算离线。
    """
    if not node.enabled:
        return False
    if node.is_local:
        return True
    if node.last_seen_at is None:
        return False
    last = node.last_seen_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    delta = (_utcnow() - last).total_seconds()
    return delta < threshold_seconds


def node_deployed_scripts(node: Node) -> dict[str, dict[str, Any]]:
    """deployed_scripts_json → dict;非法 JSON 返回 {}。agent 上报的已部署脚本事实源。"""
    if not node.deployed_scripts:
        return {}
    try:
        d = json.loads(node.deployed_scripts)
        if isinstance(d, dict):
            return d
    except json.JSONDecodeError:
        pass
    return {}


def node_pending_actions(node: Node) -> dict[str, list[str]]:
    """pending_actions_json → {"sync": [...], "delete": [...]};非法返回空两键。"""
    out: dict[str, list[str]] = {"sync": [], "delete": []}
    if not node.pending_actions:
        return out
    try:
        d = json.loads(node.pending_actions)
        if isinstance(d, dict):
            out["sync"] = [str(s) for s in d.get("sync", []) if isinstance(s, str)]
            out["delete"] = [str(s) for s in d.get("delete", []) if isinstance(s, str)]
    except json.JSONDecodeError:
        pass
    return out


def request_uninstall_script(db: Session, node_id: int, slug: str) -> None:
    """把 slug append 到节点 pending_actions.delete(去重)→ agent 下次 poll 拉到后 rm 本地 scripts/<slug>/。

    本地节点不适用(脚本在主面板,走 /scripts 删)。
    """
    node = get_node_by_id(db, node_id)
    if node.is_local:
        raise ValidationError("本地节点的脚本请在「脚本」页删除,无需下发到 agent")
    current = node_pending_actions(node)
    if slug not in current["delete"]:
        current["delete"].append(slug)
    node.pending_actions = json.dumps(
        {"sync": current["sync"], "delete": current["delete"]},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    db.flush()
    logger.info("节点 {} 下发删除脚本指令: {}", node.slug, slug)
