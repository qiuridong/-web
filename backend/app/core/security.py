"""密码哈希 + session token 生成。

详见 `进度/设计/后端架构.md` § 5.3。

- 密码:bcrypt rounds=12(2026 年合理基线;用户量小,可以慢一点)
- session token:`secrets.token_urlsafe(48)` 产生约 64 字符 url-safe 字符串
"""
from __future__ import annotations

import secrets

import bcrypt

_BCRYPT_ROUNDS = 12


def hash_password(plain: str) -> str:
    """bcrypt 哈希明文密码。

    返回 utf-8 字符串(`$2b$12$...`),直接存数据库 `password_hash` 字段。
    """
    if not plain:
        raise ValueError("密码不能为空")
    salt = bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)
    hashed = bcrypt.hashpw(plain.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """验证密码;hashed 校验失败时静默返回 False(不抛)。"""
    if not plain or not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        # bcrypt 在 hash 格式异常时会抛 ValueError
        return False


def generate_session_token() -> str:
    """生成新的 session token。

    `token_urlsafe(48)` → 约 64 字符,256 bits 熵,够用。
    """
    return secrets.token_urlsafe(48)
