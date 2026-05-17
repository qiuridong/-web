"""子进程辅助。

TODO(Batch 3 / Backend-Scheduler): 实现见 `进度/设计/后端架构.md` § 5.5。

需要的工具:
- build_subprocess_env(passthrough_keys: list[str]) -> dict[str, str]
   # 白名单基础变量(PATH, HOME, LANG, PYTHONUNBUFFERED, PYTHONIOENCODING)
   # + 调用方追加的 RUN_ID / INSTANCE_ID / SCRIPT_SLUG / DATA_DIR
   # + manifest.runtime.env_passthrough 透传(典型:HTTP_PROXY 等)
- terminate_with_grace(proc, grace_sec=5) -> None
   # SIGTERM,等待 grace_sec,仍在跑则 SIGKILL;Windows 上对应 terminate/kill
"""
from __future__ import annotations
