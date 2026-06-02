"""节点健康巡检 — 远程 agent 节点掉线检测 + 通知(去抖版)。

每 1 分钟跑一次:扫 enabled 非 local 节点,判断 ``last_seen_at`` 是否长时间无更新。
**为避免网络抖动 / 面板自身重启造成的误报**,采用三重去抖:

1. **启动宽限**(``STARTUP_GRACE_SEC``)—— 面板进程刚启动的这段时间内**完全跳过**
   评估。面板重启 / 升级时所有 agent 的心跳都会短暂失败,``last_seen_at`` 会瞬间
   显得很陈旧;给 agent 足够时间重连 + 重发心跳(agent 端 30s 一次、断网指数退避
   最多 60s)后再评估,根除"面板一重启就整片节点误报掉线"。
2. **连续确认**(``OFFLINE_CONFIRMATIONS``)—— 必须**连续 N 轮**巡检都"看起来掉线"
   才真正告警。单轮的网络/面板瞬时抖动(一两次心跳没写进库)会被滤掉。
   计数存 ``metadata_json`` 的 ``_offline_strikes``,任意一次心跳刷新即清零。
3. **较宽阈值**(``OFFLINE_THRESHOLD_SEC``)—— ``last_seen_at`` 距今超过该值才算
   "这一轮看起来掉线",默认 300s(心跳 30s 一次 ≈ 漏 10 次)。

真实掉线的告警延迟 ≈ ``OFFLINE_THRESHOLD_SEC + (OFFLINE_CONFIRMATIONS-1) * 60s``
(默认 ≈ 360s / 6 分钟),对签到面板完全可接受;换来的是几乎不再因抖动误报。

设计要点
--------
- **从没上线过的节点(last_seen_at=None)不告警** —— 它本来就没"在线"过
- 去重 / 计数标志都存 ``metadata_json``(免 migration);节点离线时无心跳覆盖该
  字段,标志稳定保留;恢复在线由本任务清除(同时清 ``_offline_strikes`` 与
  ``_offline_alerted``)
- 本任务是 **async**(需 ``await dispatch_node_event``),APScheduler AsyncIOScheduler
  以协程方式在 loop 内运行
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select

from app.db.models.node import Node
from app.db.session import SessionLocal
from app.notifications import dispatcher as _dispatcher
from app.services import node_service

# last_seen_at 距今超过该值 → 这一轮"看起来掉线"(心跳 30s 一次,300s ≈ 漏 10 次)
OFFLINE_THRESHOLD_SEC = 300
# 必须连续这么多轮巡检(每轮 60s)都看起来掉线,才真正告警 —— 去抖核心,防瞬时波动误报
OFFLINE_CONFIRMATIONS = 2
# 面板进程启动后这段时间内完全跳过评估 —— 防面板自身重启/升级触发整片节点误报
STARTUP_GRACE_SEC = 300

# 进程(模块导入)起点。node_health 模块在 scheduler 启动(_register_builtin_tasks)
# 时才被 import,≈ 进程启动时刻;用于"启动宽限"判断。
_STARTED_MONOTONIC = time.monotonic()

# metadata_json 内的去抖标志键
_KEY_STRIKES = "_offline_strikes"
_KEY_ALERTED = "_offline_alerted"


async def node_health_job() -> None:
    """每分钟被 APScheduler 调用(async)。"""
    try:
        # ① 启动宽限:面板刚起步,先别评估,给 agent 重连 + 重发心跳的时间
        uptime = time.monotonic() - _STARTED_MONOTONIC
        if uptime < STARTUP_GRACE_SEC:
            logger.debug(
                "node_health: 启动宽限期内({:.0f}s < {}s),跳过本轮",
                uptime,
                STARTUP_GRACE_SEC,
            )
            return

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
                # 记录处理前的标志,最后只在变化时回写(减少无谓 DB 写)
                before = (meta.get(_KEY_ALERTED), meta.get(_KEY_STRIKES))
                alerted = bool(meta.get(_KEY_ALERTED))
                strikes = int(meta.get(_KEY_STRIKES) or 0)

                last = node.last_seen_at
                if last is None:
                    # 从没上线过 → 不告警;顺手清掉任何历史标记
                    meta.pop(_KEY_STRIKES, None)
                    meta.pop(_KEY_ALERTED, None)
                else:
                    if last.tzinfo is None:
                        last = last.replace(tzinfo=timezone.utc)
                    silent_sec = (now - last).total_seconds()

                    if silent_sec > OFFLINE_THRESHOLD_SEC:
                        # ② 这一轮看起来掉线 → 累加确认计数
                        strikes += 1
                        meta[_KEY_STRIKES] = strikes
                        if strikes >= OFFLINE_CONFIRMATIONS and not alerted:
                            sent = await _dispatcher.dispatch_node_event(
                                db, node, "node_offline"
                            )
                            meta[_KEY_ALERTED] = True
                            logger.info(
                                "节点掉线告警 node={} 已发送 {} 渠道"
                                "(静默 {:.0f}s / 连续 {} 轮确认)",
                                node.slug,
                                sent,
                                silent_sec,
                                strikes,
                            )
                        else:
                            logger.debug(
                                "node_health: {} 疑似掉线 strike={}/{} 静默 {:.0f}s"
                                "(未达确认或已告警过)",
                                node.slug,
                                strikes,
                                OFFLINE_CONFIRMATIONS,
                                silent_sec,
                            )
                    else:
                        # 心跳新鲜 → 在线;清确认计数,若曾告警则清标志(恢复)
                        if alerted:
                            logger.info(
                                "节点恢复在线,清掉线告警标志 node={}", node.slug
                            )
                        meta.pop(_KEY_STRIKES, None)
                        meta.pop(_KEY_ALERTED, None)

                after = (meta.get(_KEY_ALERTED), meta.get(_KEY_STRIKES))
                if after != before:
                    node.metadata_json = json.dumps(meta, ensure_ascii=False)
                    changed = True

            if changed:
                db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("node_health_job 失败: {}", exc)
