"""seed_scripts — 一键安装/手动用：把 seed/scripts/ 幂等导入货架。

容器内运行（workdir /app）：
    python seed_scripts.py
输出：
    SEED_SCRIPTS_OK: <新导入数量>
"""
from __future__ import annotations

from app.services.seed import seed_initial_scripts

if __name__ == "__main__":
    count = seed_initial_scripts()
    print(f"SEED_SCRIPTS_OK: {count}")
    raise SystemExit(0)
