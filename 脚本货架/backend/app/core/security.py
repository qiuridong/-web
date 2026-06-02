"""密码哈希 + session token 生成（移植自主项目 ``backend/app/core/security.py``）。

- 密码：bcrypt rounds=12
- session token：``secrets.token_urlsafe(48)`` 约 64 字符
"""
from __future__ import annotations

import secrets

import bcrypt

_BCRYPT_ROUNDS = 12


def hash_password(plain: str) -> str:
    """bcrypt 哈希明文密码，返回 ``$2b$12$...`` 字符串。"""
    if not plain:
        raise ValueError("密码不能为空")
    salt = bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)
    return bcrypt.hashpw(plain.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """验证密码；hash 格式异常时静默返回 False。"""
    if not plain or not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def generate_session_token() -> str:
    """生成新的 session token（约 64 字符，256 bits 熵）。"""
    return secrets.token_urlsafe(48)
