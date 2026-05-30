"""节点健康巡检 — 远程 agent 节点掉线检测 + 通知。

每 1 分钟跑一次:扫 enabled 非 local 节点,``last_seen_at`` 超过阈值(默认 180s,
约漏 6 次心跳)→ 判定掉线 → 若未告警过则 ``dispatch_node_event(node_offline)``
+ 在 ``node.metadata`` 标 ``_offline_alerted``;恢复在线则清标志(避免重复告警)。

设计要点
--------
- **从没上线过的节点(last_seen_at=None)不告警** —— 它本来就没"在线"过
- 去重标志存 ``metadata_json`` 的 ``_offline_alerted``(免 migration);节点离线时
  无心跳覆盖该字段,标志稳定保留;恢复在线由本任务清除
- 本任务是 **async**(需 ``await dispatch_node_event``),APScheduler AsyncIOScheduler
  以协程方式在 loop 内运行
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select

from app.db.models.node import Node
from app.db.session import SessionLocal
from app.notifications import dispatcher as _dispatcher
from app.services import node_service

# 掉线阈值:心跳 30s 一次,180s = 漏约 6 次才告警,避免网络抖动误报
OFFLINE_THRESHOLD_SEC = 180


async def node_health_job() -> None:
    """每分钟被 APScheduler 调用(async)。"""
    try:
        with SessionLocal() as db:
            now = datetime.now(timezone.utc)
            nodes = list(
                db.scalars(
                    select(Node).where(
                        Node.enabled.is_(True),
                        Node.is_local.is_(False),
                    )
                ).all()
            )
            changed = False
            for node in nodes:
                meta = node_service.node_metadata_dict(node)
                alerted = bool(meta.get("_offline_alerted"))
                last = node.last_seen_at
                if last is None:
                    # 从没上线过 → 不告警
                    continue
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                offline = (now - last).total_seconds() > OFFLINE_THRESHOLD_SEC

                if offline and not alerted:
                    sent = await _dispatcher.dispatch_node_event(
                        db, node, "node_offline"
                    )
                    meta["_offline_alerted"] = True
                    node.metadata_json = json.dumps(meta, ensure_ascii=False)
                    changed = True
                    logger.info(
                        "节点掉线告警 node={} 已发送 {} 渠道", node.slug, sent
                    )
                elif (not offline) and alerted:
                    meta.pop("_offline_alerted", None)
                    node.metadata_json = json.dumps(meta, ensure_ascii=False)
                    changed = True
                    logger.info("节点恢复在线,清掉线告警标志 node={}", node.slug)

            if changed:
                db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("node_health_job 失败: {}", exc)
