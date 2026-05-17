"""时间相关工具 — ISO 解析、now() 包装、时区转换。

TODO(各 agent): 按需实现,典型函数:
- utc_now() -> datetime                    # UTC tz-aware
- to_user_tz(dt, tz_str) -> datetime
- parse_iso(s) -> datetime                 # 接受带 / 不带时区
- format_iso_utc(dt) -> str                # `2026-05-15T00:00:00Z`

详见 `进度/设计/后端架构.md` § 4.6 时区处理章节。
"""
from __future__ import annotations
