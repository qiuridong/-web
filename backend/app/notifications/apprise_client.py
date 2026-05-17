"""apprise 客户端 + 实例池。

实现见 `进度/设计/后端架构.md` § 2.5。

公开
----
- ``AppriseClientPool`` 单例 — 内部缓存 ``dict[channel_id, Apprise]`` 避免每次 send 重建
- ``async send(channel_id, channel_type, apprise_url, title, body, body_format='markdown')
   -> tuple[bool, float, str | None]`` — 返回 ``(ok, latency_ms, error_msg)``
- ``mask_apprise_url(url) -> str`` — 脱敏 ``<scheme>://***/***``
- ``invalidate_channel(channel_id)`` — channel 被更新/删除时清缓存

依赖 ``apprise`` 库。失败**不抛异常**,而是返回 ``(False, latency_ms, error)`` —
让 dispatcher 知道结果但不打断整体流程(一个渠道失败不影响其他渠道)。
"""
from __future__ import annotations

import asyncio
import time
from typing import Any
from urllib.parse import urlparse

import apprise
from loguru import logger


# ============================================================
# 脱敏
# ============================================================
def mask_apprise_url(url: str) -> str:
    """把 apprise URL 脱敏为 ``<scheme>://***/***``。

    用途:GET 渠道列表/详情时给前端展示 — 既能让用户认出渠道类型,
    又不暴露 token / chat_id / webhook 路径。

    异常 URL(无 scheme)→ ``"***"``。
    """
    if not url:
        return "***"
    try:
        parsed = urlparse(url)
        scheme = parsed.scheme or ""
        if not scheme:
            return "***"
        return f"{scheme}://***/***"
    except Exception:  # noqa: BLE001 pragma: no cover
        return "***"


# ============================================================
# 实例池
# ============================================================
class AppriseClientPool:
    """每个 channel_id 缓存一个 ``apprise.Apprise`` 实例,避免每次 send 重建。

    线程安全:用 asyncio.Lock 保护 ``_cache``;同步路径用 GIL 兜底
    (Apprise 实例自身是并发安全的 — 它内部用 requests/aiohttp,不可变状态)。
    """

    def __init__(self) -> None:
        self._cache: dict[int, apprise.Apprise] = {}
        self._lock = asyncio.Lock()

    def _build_for(self, apprise_url: str) -> apprise.Apprise:
        """构造单 URL 的 Apprise 实例。"""
        client = apprise.Apprise()
        added = client.add(apprise_url)
        if not added:
            # add 失败通常是 URL 格式不支持(apprise 自身会写一条 logging.error)
            # 我们仍然返回 client(其 notify 会失败),让上层得到一致的错误流
            logger.warning(
                "apprise.add 返回 False,URL 可能不被识别(已脱敏的 scheme={})",
                mask_apprise_url(apprise_url).split(":")[0],
            )
        return client

    async def get(self, channel_id: int, apprise_url: str) -> apprise.Apprise:
        """取缓存或构造新实例。"""
        async with self._lock:
            client = self._cache.get(channel_id)
            if client is None:
                client = self._build_for(apprise_url)
                self._cache[channel_id] = client
            return client

    async def invalidate(self, channel_id: int) -> None:
        """渠道被改/删时调用,清除缓存(下次 get 重建)。"""
        async with self._lock:
            self._cache.pop(channel_id, None)

    async def invalidate_all(self) -> None:
        async with self._lock:
            self._cache.clear()

    # ============================================================
    # send
    # ============================================================
    async def send(
        self,
        *,
        channel_id: int,
        channel_type: str,  # noqa: ARG002 — 预留扩展;v1 只有 apprise
        apprise_url: str,
        title: str,
        body: str,
        body_format: str = "markdown",
    ) -> tuple[bool, float, str | None]:
        """异步发送一条通知。

        返回
        ----
        ``(ok, latency_ms, error_msg)``

        - ``ok``:apprise.notify 是否成功
        - ``latency_ms``:发送耗时(毫秒;包含网络往返)
        - ``error_msg``:失败时的错误描述(成功为 ``None``)

        说明:apprise 的 notify 在某些渠道(SMTP/HTTP)是阻塞 IO,
        我们用 ``asyncio.to_thread`` 包一层避免堵 event loop。
        """
        start = time.perf_counter()
        try:
            client = await self.get(channel_id, apprise_url)
        except Exception as exc:  # noqa: BLE001
            latency = (time.perf_counter() - start) * 1000
            return False, latency, f"构造 apprise 客户端失败: {exc}"

        # apprise body_format 映射
        bf = self._normalize_body_format(body_format)

        def _do_send() -> tuple[bool, str | None]:
            try:
                ok = client.notify(title=title, body=body, body_format=bf)
                if not ok:
                    return False, "apprise.notify 返回 False(渠道未送达或被拒绝)"
                return True, None
            except Exception as exc:  # noqa: BLE001
                return False, f"{type(exc).__name__}: {exc}"

        try:
            ok, err = await asyncio.to_thread(_do_send)
        except Exception as exc:  # noqa: BLE001 pragma: no cover
            ok, err = False, f"to_thread 抛出: {exc}"

        latency = (time.perf_counter() - start) * 1000
        if ok:
            logger.info(
                "通知发送成功 channel_id={} latency_ms={:.0f}",
                channel_id,
                latency,
            )
        else:
            logger.warning(
                "通知发送失败 channel_id={} latency_ms={:.0f} err={}",
                channel_id,
                latency,
                err,
            )
        return ok, latency, err

    @staticmethod
    def _normalize_body_format(value: str | None) -> Any:
        """把字符串 body_format 转 apprise NotifyFormat 枚举。"""
        if not value:
            return apprise.NotifyFormat.MARKDOWN
        v = value.lower()
        if v in ("markdown", "md"):
            return apprise.NotifyFormat.MARKDOWN
        if v in ("html",):
            return apprise.NotifyFormat.HTML
        if v in ("text", "txt", "plain"):
            return apprise.NotifyFormat.TEXT
        return apprise.NotifyFormat.MARKDOWN


# ============================================================
# 单例
# ============================================================
_pool: AppriseClientPool | None = None


def get_pool() -> AppriseClientPool:
    """获取全局 pool 单例。"""
    global _pool
    if _pool is None:
        _pool = AppriseClientPool()
    return _pool


def reset_pool() -> None:
    """单测/重置用 — 清空单例。"""
    global _pool
    _pool = None
