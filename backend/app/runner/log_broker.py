"""实时日志 broker — per-run asyncio.Queue 广播 stdout/stderr 给 SSE 订阅者。

实现见 `进度/设计/后端架构.md` § 2.4.1。

设计要点
--------
- 每个 run_id 对应一个 :class:`RunLogChannel`,内含若干订阅者队列
- 主程序(executor)在子进程产生 stdout/stderr 时调用 :meth:`publish`,
  channel 把消息丢给所有订阅者队列
- SSE 路由侧 :meth:`subscribe` 返回 ``AsyncIterator`` 直接 ``async for``
- run 结束后 :meth:`close` 广播 ``end`` 事件并清掉所有订阅者
- 单 run 订阅者数硬上限(默认 10),超出 :meth:`subscribe` 抛
  :class:`app.core.exceptions.ResourceLimitError`

线程模型
--------
- 所有操作在主 event loop 上做(executor / SSE 都是同进程 async)
- 不跨进程,sandbox 子进程的输出由 executor 主程序读后再 ``publish``

事件 dict 形态(给 SSE 用)
--------------------------
- ``{"event": "stdout", "data": "..."}``
- ``{"event": "stderr", "data": "..."}``
- ``{"event": "status", "data": {...}}``
- ``{"event": "end", "data": ""}``  (channel close 时自动广播)
"""
from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from typing import Any

from app.core.exceptions import ResourceLimitError

#: 单 run 订阅者数硬上限(SSE 客户端数)
DEFAULT_MAX_SUBSCRIBERS = 10

#: 每个订阅者队列上限(防止慢消费者把内存撑爆)
DEFAULT_QUEUE_SIZE = 2048

#: 广播 close 事件时使用的事件名
_END_EVENT = "end"


class _Subscriber:
    """单个订阅者持有一个 asyncio.Queue。"""

    __slots__ = ("queue", "closed")

    def __init__(self, queue_size: int) -> None:
        self.queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(
            maxsize=queue_size
        )
        self.closed: bool = False


class RunLogChannel:
    """一个 run 对应一个 channel,内含订阅者队列。"""

    def __init__(
        self,
        run_id: int,
        *,
        max_subscribers: int = DEFAULT_MAX_SUBSCRIBERS,
        queue_size: int = DEFAULT_QUEUE_SIZE,
    ) -> None:
        self.run_id = run_id
        self._subs: list[_Subscriber] = []
        self._max_subs = max_subscribers
        self._queue_size = queue_size
        self._closed: bool = False

    @property
    def subscriber_count(self) -> int:
        return len(self._subs)

    @property
    def closed(self) -> bool:
        return self._closed

    # ============================================================
    # 发布(主程序侧)
    # ============================================================
    def publish(self, stream: str, line: str) -> None:
        """广播一行 stdout/stderr 给所有订阅者。

        :param stream: ``"stdout"`` / ``"stderr"``
        :param line: 单行文本(无 ``\\n``)
        """
        if self._closed:
            return
        evt = {"event": stream, "data": line}
        self._broadcast(evt)

    def publish_status(self, payload: dict[str, Any]) -> None:
        """广播 status 事件(running / success / failure / ...)。"""
        if self._closed:
            return
        self._broadcast({"event": "status", "data": payload})

    def close(self) -> None:
        """关闭 channel 并广播 end 事件;subscribers 队列收到 None 退出。"""
        if self._closed:
            return
        self._closed = True
        self._broadcast({"event": _END_EVENT, "data": ""})
        # 给每个订阅者额外发一个 None 作为 sentinel,确保 async for 立刻退出
        for sub in list(self._subs):
            sub.closed = True
            with contextlib.suppress(asyncio.QueueFull):
                sub.queue.put_nowait(None)
        self._subs.clear()

    def _broadcast(self, evt: dict[str, Any]) -> None:
        # 复制一份避免迭代时被改;失败的订阅者就丢消息(慢消费者保护)
        dropped: list[_Subscriber] = []
        for sub in list(self._subs):
            if sub.closed:
                dropped.append(sub)
                continue
            try:
                sub.queue.put_nowait(evt)
            except asyncio.QueueFull:
                # 慢消费者:静默丢消息(不阻塞主流程)
                # 真实场景应在订阅者侧检测 lag,这里 v1 简化
                dropped.append(sub)
                sub.closed = True
        for sub in dropped:
            with contextlib.suppress(ValueError):
                self._subs.remove(sub)

    # ============================================================
    # 订阅(SSE 侧)
    # ============================================================
    async def subscribe(self) -> AsyncIterator[dict[str, Any]]:
        """订阅本 channel,async-for 消费事件直到 close。

        :raises ResourceLimitError: 订阅者超出 ``max_subscribers``
        """
        if self._closed:
            # 已 close → 立即产出一个 end 事件,然后结束
            yield {"event": _END_EVENT, "data": ""}
            return

        if len(self._subs) >= self._max_subs:
            raise ResourceLimitError(
                f"run {self.run_id} 实时日志订阅者已达上限 {self._max_subs}",
                details={
                    "run_id": self.run_id,
                    "max_subscribers": self._max_subs,
                },
            )

        sub = _Subscriber(self._queue_size)
        self._subs.append(sub)

        try:
            while True:
                evt = await sub.queue.get()
                if evt is None:
                    # close sentinel
                    return
                yield evt
                if evt.get("event") == _END_EVENT:
                    return
        finally:
            sub.closed = True
            with contextlib.suppress(ValueError):
                self._subs.remove(sub)


class LogBroker:
    """全局 broker:按 run_id 管理 :class:`RunLogChannel`。

    单例;通过 :func:`get_log_broker` 获取。
    """

    def __init__(
        self,
        *,
        max_subscribers: int = DEFAULT_MAX_SUBSCRIBERS,
        queue_size: int = DEFAULT_QUEUE_SIZE,
    ) -> None:
        self._channels: dict[int, RunLogChannel] = {}
        self._max_subs = max_subscribers
        self._queue_size = queue_size

    def get_or_create(self, run_id: int) -> RunLogChannel:
        """获取 channel;不存在则创建一个新的。"""
        ch = self._channels.get(run_id)
        if ch is None or ch.closed:
            ch = RunLogChannel(
                run_id,
                max_subscribers=self._max_subs,
                queue_size=self._queue_size,
            )
            self._channels[run_id] = ch
        return ch

    def get(self, run_id: int) -> RunLogChannel | None:
        """获取已存在的 channel(可能为 None)。"""
        return self._channels.get(run_id)

    def publish(self, run_id: int, stream: str, line: str) -> None:
        """便捷:向 ``run_id`` 的 channel 发一行。"""
        ch = self.get_or_create(run_id)
        ch.publish(stream, line)

    def publish_status(self, run_id: int, payload: dict[str, Any]) -> None:
        ch = self.get_or_create(run_id)
        ch.publish_status(payload)

    def close(self, run_id: int) -> None:
        """关闭并从注册表移除某 run 的 channel。"""
        ch = self._channels.pop(run_id, None)
        if ch is not None:
            ch.close()

    def shutdown(self) -> None:
        """关闭所有 channel(app shutdown 时调)。"""
        for ch in list(self._channels.values()):
            ch.close()
        self._channels.clear()


_broker_singleton: LogBroker | None = None


def get_log_broker() -> LogBroker:
    """全局单例。"""
    global _broker_singleton
    if _broker_singleton is None:
        _broker_singleton = LogBroker()
    return _broker_singleton


def reset_log_broker() -> None:
    """单元测试用:重置单例。"""
    global _broker_singleton
    if _broker_singleton is not None:
        _broker_singleton.shutdown()
    _broker_singleton = None
