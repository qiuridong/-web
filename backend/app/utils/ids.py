"""ID / token / nonce 生成工具。

TODO(各 agent): 按需实现,典型函数:
- new_nonce(n_bytes=16) -> str            # 短随机串(用于 trace_id 等)
- new_uuid7() -> str                       # 时间排序友好的 UUID(若安装 uuid7 库)
- new_session_token() -> str               # 见 app.core.security.generate_session_token
"""
from __future__ import annotations
