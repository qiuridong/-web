"""失败重试策略 — 指数退避计算。

实现见 `进度/设计/后端架构.md` § 4.5。

公式
----
第 ``n`` 次重试的等待秒数 = ``retry_interval_sec * 2^(n-1)``,封顶 ``RETRY_CAP_SEC``(1 小时)。

- ``n=1`` 即首次重试,等待 ``interval``
- ``n=2`` 等待 ``2 * interval``
- ``n=3`` 等待 ``4 * interval``
- ...

调用方负责传 ``attempt`` 字段(从 1 起,首次执行 = 1)。
"""
from __future__ import annotations

#: 单次重试间隔上限(秒),设计稿 § 4.5
RETRY_CAP_SEC: int = 3600


def compute_retry_delay(
    *,
    retry_interval_sec: int,
    attempt: int,
    cap_sec: int = RETRY_CAP_SEC,
) -> int:
    """计算下一次 retry 的延迟秒数(指数退避 + cap)。

    :param retry_interval_sec: instance 配置的首次重试等待
    :param attempt: 本次完成的 attempt(>=1);下一次将是 attempt+1
                     但等待公式按"第 attempt 次重试"算,即
                     首次重试 attempt=1 时 wait = interval * 1
    :param cap_sec: 单次重试间隔上限
    :returns: 下一次 attempt 触发前的等待秒数

    实际语义(与设计稿一致):
        首次失败(attempt=1) → 下次重试等待 retry_interval_sec
        二次失败(attempt=2) → 下次重试等待 retry_interval_sec * 2
        三次失败(attempt=3) → 等待 retry_interval_sec * 4
        ...
    """
    if retry_interval_sec < 1:
        retry_interval_sec = 1
    if attempt < 1:
        attempt = 1
    # 第 n 次失败后触发第 n+1 次 attempt 的等待 = interval * 2^(n-1)
    # 这里我们把"刚结束的 attempt"作为 n
    exp = max(0, attempt - 1)
    delay = retry_interval_sec * (2**exp)
    return int(min(delay, cap_sec))


def should_retry(
    *,
    success: bool,
    status: str,
    attempt: int,
    max_retries: int,
) -> bool:
    """判断是否应触发重试。

    设计稿 § 4.5:
    - ``max_retries`` = 0 → 不重试
    - 成功(status=success)→ 不重试
    - 已达 max_retries → 不重试
    - 手动取消(status=cancelled)→ 不重试
    """
    if max_retries <= 0:
        return False
    if success:
        return False
    if status in ("success", "cancelled"):
        return False
    return attempt <= max_retries  # attempt 是刚结束的次数;还要再 retry
