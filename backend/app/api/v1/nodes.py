"""节点管理 API(admin 端,走 session auth)— `/api/v1/nodes/*`。

MVP-1 远程 agent,设计稿:`进度/设计/远程VPS脚本执行调研.md` § 5 / § 7。

端点清单(6 个)
---------------
- GET    /nodes                         🔒 列表(含 online 派生)
- POST   /nodes                         🔒 创建,返回**一次性** 明文 token
- GET    /nodes/{id}                    🔒 详情
- PATCH  /nodes/{id}                    🔒 改 name/description/enabled
- POST   /nodes/{id}/regenerate-token   🔒 重新生成 token
- DELETE /nodes/{id}                    🔒 删除(local 不可删;有 instance 关联时拒)

业务异常统一抛 ``app.core.exceptions.*``,由 ``error_handler`` 转标准响应。
"""
from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.db.models.node import Node
from app.deps import CurrentUser, DBSession
from app.schemas.node import (
    NodeCreate,
    NodeCreateResponse,
    NodeDetail,
    NodeListItem,
    NodeListResponse,
    NodeTokenResponse,
    NodeUpdate,
)
from app.services import node_service

router = APIRouter(prefix="/nodes", tags=["nodes"])


# ============================================================
# 序列化辅助
# ============================================================
def _node_to_item(node: Node) -> NodeListItem:
    """Node ORM → NodeListItem(含 online 派生 + metadata 反序列化)。"""
    return NodeListItem(
        id=node.id,
        slug=node.slug,
        name=node.name,
        description=node.description,
        is_local=bool(node.is_local),
        last_seen_at=node.last_seen_at,
        version=node.version,
        metadata=node_service.node_metadata_dict(node),
        enabled=bool(node.enabled),
        online=node_service.is_node_online(node),
        created_at=node.created_at,
        updated_at=node.updated_at,
    )


def _node_to_detail(node: Node) -> NodeDetail:
    item = _node_to_item(node)
    return NodeDetail(
        **item.model_dump(),
        deployed_scripts=node_service.node_deployed_scripts(node),
        pending_actions=node_service.node_pending_actions(node),
    )


# ============================================================
# 列表
# ============================================================
@router.get(
    "",
    response_model=NodeListResponse,
    summary="节点列表(含 online 派生状态)",
)
def list_nodes(
    db: DBSession,
    _user: CurrentUser,
) -> NodeListResponse:
    """🔒 列表(按 id 升序;local 永远在最前)。"""
    nodes = node_service.list_nodes(db)
    items = [_node_to_item(n) for n in nodes]
    return NodeListResponse(items=items, total=len(items))


# ============================================================
# 创建
# ============================================================
@router.post(
    "",
    response_model=NodeCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建节点(返回一次性明文 token)",
)
def create_node(
    payload: NodeCreate,
    db: DBSession,
    _user: CurrentUser,
) -> NodeCreateResponse:
    """🔒 创建一个新远程 agent 节点。

    **重要**:响应里的 ``token`` 字段是明文,**仅此一次返回**。
    前端必须显示给用户保存,关闭弹窗后无法再取(DB 只存 bcrypt hash)。
    丢失只能 ``POST /nodes/{id}/regenerate-token``。
    """
    node, token = node_service.create_node(
        db,
        slug=payload.slug,
        name=payload.name,
        description=payload.description,
    )
    db.commit()
    return NodeCreateResponse(
        node=_node_to_detail(node),
        token=token,
    )


# ============================================================
# 详情
# ============================================================
@router.get(
    "/{node_id}",
    response_model=NodeDetail,
    summary="节点详情",
)
def get_node(
    node_id: int,
    db: DBSession,
    _user: CurrentUser,
) -> NodeDetail:
    """🔒 详情。"""
    node = node_service.get_node_by_id(db, node_id)
    return _node_to_detail(node)


# ============================================================
# 更新
# ============================================================
@router.patch(
    "/{node_id}",
    response_model=NodeDetail,
    summary="更新节点(name/description/enabled)",
)
def update_node(
    node_id: int,
    payload: NodeUpdate,
    db: DBSession,
    _user: CurrentUser,
) -> NodeDetail:
    """🔒 部分更新。

    限制:本地节点 enabled 不可改为 False。
    """
    node = node_service.update_node(
        db,
        node_id,
        name=payload.name,
        description=payload.description,
        enabled=payload.enabled,
    )
    db.commit()
    return _node_to_detail(node)


# ============================================================
# 重新生成 token
# ============================================================
@router.post(
    "/{node_id}/regenerate-token",
    response_model=NodeTokenResponse,
    summary="重新生成节点 token(旧 token 立即失效)",
)
def regenerate_token(
    node_id: int,
    db: DBSession,
    _user: CurrentUser,
) -> NodeTokenResponse:
    """🔒 旧 token 立即失效;新明文 token 仅此一次返回。"""
    token = node_service.regenerate_token(db, node_id)
    db.commit()
    return NodeTokenResponse(token=token)


# ============================================================
# 删除
# ============================================================
@router.delete(
    "/{node_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除节点(local 不可删;有 instance 时拒)",
)
def delete_node(
    node_id: int,
    response: Response,
    db: DBSession,
    _user: CurrentUser,
) -> Response:
    """🔒 删除节点。

    限制:
    - 本地节点(is_local=1)永远不可删
    - 有 instance 关联时拒绝(用户必须先迁移 instance.node_id 到其它节点)
    """
    node_service.delete_node(db, node_id)
    db.commit()
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


# ============================================================
# 卸载节点上已部署的脚本(下发 pending_actions.delete)
# ============================================================
@router.post(
    "/{node_id}/deployed-scripts/{slug}/uninstall",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="卸载节点上已部署的脚本(下发删除指令,agent 拉取后 rm)",
)
def uninstall_node_script(
    node_id: int,
    slug: str,
    response: Response,
    db: DBSession,
    _user: CurrentUser,
) -> Response:
    """🔒 把 slug 加入节点 ``pending_actions.delete``。

    agent 下次 poll 拉到后删本地 ``scripts/<slug>/``,再 inventory-report ack →
    主面板从 ``deployed_scripts`` 移除。本地节点不适用(脚本在主面板,走 ``/scripts`` 删)。
    """
    node_service.request_uninstall_script(db, node_id, slug)
    db.commit()
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
