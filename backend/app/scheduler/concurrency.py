"""并发槽位控制 — 全局 asyncio.Semaphore + 排队公平性。

实现见 `进度/设计/后端架构.md` § 4.4 步骤 [1]。

设计要点
--------
- 同进程最多 ``max_concurrent`` 个脚本同时跑(默认 4)
- 满则后续 ``acquire()`` 自然 await(Semaphore 是 FIFO 公平的)
- ``acquire()`` 是 async 的;用 ``async with slot:`` 自动 release
- 容量是模块级 sigleton,改 settings 后重建(v1 不动态改)
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

#: 默认并发上限(取自设计稿 § 1.8 settings.concurrent_runs_max)
DEFAULT_MAX_CONCURRENT: int = 4


class ConcurrencyLimiter:
    """asyncio.Semaphore 的薄包装,提供 metrics + async-with 接口。"""

    def __init__(self, max_concurrent: int = DEFAULT_MAX_CONCURRENT) -> None:
        if max_concurrent < 1:
            raise ValueError("max_concurrent 必须 >= 1")
        self._max = max_concurrent
        self._sem = asyncio.Semaphore(max_concurrent)
        self._active: int = 0

    @property
    def max_concurrent(self) -> int:
        return self._max

    @property
    def active(self) -> int:
        return self._active

    @property
    def available(self) -> int:
        return max(0, self._max - self._active)

    @asynccontextmanager
    async def slot(self) -> AsyncIterator[None]:
        """async-with 自动 acquire / release。

        用法::

            async with limiter.slot():
                await run_script(...)
        """
        await self._sem.acquire()
        self._active += 1
        try:
            yield
        finally:
            self._active -= 1
            self._sem.release()


_limiter_singleton: ConcurrencyLimiter | None = None


def get_limiter() -> ConcurrencyLimiter:
    """全局单例。"""
    global _limiter_singleton
    if _limiter_singleton is None:
        _limiter_singleton = ConcurrencyLimiter()
    return _limiter_singleton


def reset_limiter(max_concurrent: int = DEFAULT_MAX_CONCURRENT) -> ConcurrencyLimiter:
    """单元测试用 / 启动时按 settings 重建。"""
    global _limiter_singleton
    _limiter_singleton = ConcurrencyLimiter(max_concurrent)
    return _limiter_singleton
