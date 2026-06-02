"""seed_admin — 一键安装用：无用户时创建首个管理员 + 打印结果（幂等）。

容器内运行（workdir /app）：
    python seed_admin.py --username admin --password '<强随机密码>'
或用环境变量 ADMIN_USERNAME / ADMIN_PASSWORD。

约定输出（供 install-hub.sh 解析）：
    SEED_OK: <username>      成功创建
    SEED_SKIP: ...           已存在用户，跳过
    SEED_ERR: ...            参数/校验错误（stderr）
"""
from __future__ import annotations

import argparse
import os
import sys


def main() -> int:
    ap = argparse.ArgumentParser(description="seed first admin user (idempotent)")
    ap.add_argument("--username", default=os.environ.get("ADMIN_USERNAME", "admin"))
    ap.add_argument("--password", default=os.environ.get("ADMIN_PASSWORD", ""))
    args = ap.parse_args()

    if not args.password:
        print("SEED_ERR: 缺少 --password 或 ADMIN_PASSWORD", file=sys.stderr)
        return 2

    from app.core.exceptions import ConflictError, ValidationError
    from app.db.session import SessionLocal
    from app.services import auth_service

    with SessionLocal() as db:
        if not auth_service.is_setup_required(db):
            print("SEED_SKIP: 已存在用户，跳过（请用现有账号登录）")
            return 0
        try:
            user = auth_service.create_admin(db, username=args.username, password=args.password)
            db.commit()
            print(f"SEED_OK: {user.username}")
            return 0
        except ConflictError:
            print("SEED_SKIP: 并发下已被创建，跳过")
            return 0
        except ValidationError as exc:
            print(f"SEED_ERR: {exc}", file=sys.stderr)
            return 3


if __name__ == "__main__":
    raise SystemExit(main())
