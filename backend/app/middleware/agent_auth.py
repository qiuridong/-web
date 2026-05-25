"""Agent 端 Bearer Token 鉴权依赖。

MVP-1 远程 agent,设计稿:`进度/设计/远程VPS脚本执行调研.md` § 5.1。

设计要点
--------
- agent 端调用 ``/api/v1/agent/*`` 时携带 ``Authorization: Bearer sa_xxx``
- 校验流程:
  1. 从 ``Authorization`` 头取 token
  2. 调 ``node_service.authenticate_agent(db, token)`` 全表 bcrypt 校验
  3. 命中 → 注入 ``request.state.agent_node``,返回 ``Node``
  4. 未命中 → 抛 ``AuthError`` 401(由 ``error_handler`` 兜底)

这里**不写 middleware 类**(全局拦截),而是写 FastAPI Depends,
单独挂到 ``/api/v1/agent/*`` 路由上,避免影响其它路径。

CSRF 豁免
----------
``CSRFMiddleware`` 对 ``/api/v1/agent/*`` 路径已经豁免(见 csrf.py)。
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.core.exceptions import AuthError
from app.db.models.node import Node
from app.deps import DBSession
from app.services import node_service


def get_agent_node(
    request: Request,
    db: DBSession,
) -> Node:
    """从 ``Authorization: Bearer <token>`` 头取 token → 鉴权 → 返回 Node。

    :raises AuthError: token 缺失 / 形态错误 / 鉴权失败 / 节点已禁用
    """
    auth_header = request.headers.get("Authorization") or ""
    if not auth_header:
        raise AuthError(
            "缺少 Authorization 头",
            details={"hint": "agent 应携带 'Authorization: Bearer sa_xxx'"},
        )
    parts = auth_header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise AuthError(
            "Authorization 头格式错误,应为 'Bearer <token>'",
            details={"hint": "agent 应携带 'Authorization: Bearer sa_xxx'"},
        )
    token = parts[1].strip()
    node = node_service.authenticate_agent(db, token)
    if node is None:
        raise AuthError(
            "agent token 鉴权失败",
            details={"hint": "检查 token 是否正确或节点是否被禁用"},
        )
    # 缓存到 request.state,供下游使用
    request.state.agent_node = node
    return node


# FastAPI 类型注解(供 agent 路由使用 ``node: AgentNode``)
AgentNode = Annotated[Node, Depends(get_agent_node)]
