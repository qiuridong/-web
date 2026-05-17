"""Fernet 主密钥管理 + 字段级加解密。

详见 `进度/设计/后端架构.md` § 5.1 / § 5.2。

核心契约:
- 密钥文件存于 `settings.encryption_key_path`(默认 `data/encryption.key`)
- 不存在则自动生成,并以 `0o600` 权限写入(Windows 上 chmod 静默忽略)
- 启动时强警告 "请异地离线备份密钥,丢失则所有 secret 失效"
- 单例 `get_cipher()` 提供 `encrypt/decrypt` + `encrypt_dict/decrypt_dict` 包装
- 用 `MultiFernet` 占位单 key,为将来 key rotation 预留(详见 § 5.1 末段)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from cryptography.fernet import Fernet, MultiFernet
from loguru import logger

from app.config import get_settings

_FILE_MODE = 0o600


def load_or_create_key(path: Path) -> bytes:
    """加载或生成 Fernet 主密钥。

    返回 base64 url-safe bytes(32 字节解码后)。

    新建时:
    1. 写文件,chmod 0o600(Windows 上失败时静默忽略)
    2. stderr 打印一条**强警告**(无论 LOG_LEVEL 都可见)
    """
    path = Path(path)

    if path.exists():
        key = path.read_bytes().strip()
        if not key:
            raise ValueError(f"加密密钥文件为空: {path}")
        # Fernet 接受 base64 url-safe 32 字节 → 编码 44 字符
        # 这里只验长度,Fernet 自身在解码时会再次校验
        return key

    # ===== 生成新密钥 =====
    path.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    path.write_bytes(key)

    # 权限 0o600;Windows 上 os.chmod 行为不同,失败不致命
    try:
        os.chmod(path, _FILE_MODE)
    except (OSError, NotImplementedError):  # pragma: no cover
        pass

    # 强警告 — 直接 stderr,绕过 LOG_LEVEL,确保任何环境都看得到
    msg = (
        "\n"
        "============================================================\n"
        "  [!] 已生成新的 Fernet 加密主密钥\n"
        f"      路径: {path}\n"
        "      请立即【异地离线备份】此文件(密码管理器 / 离线介质)\n"
        "      此文件丢失 = 所有 secret 配置永久无法解密\n"
        "      此文件泄露 = 攻击者可解密所有 secret 字段\n"
        "============================================================\n"
    )
    print(msg, file=sys.stderr, flush=True)
    logger.warning("已生成新的加密主密钥 path={}", path)

    return key


class FernetCipher:
    """Fernet 加密/解密包装。

    内部用 `MultiFernet`:第一个 key 用于加密,所有 key 都尝试解密。
    v1 只有一个 key,但这层包装让将来加 rotation key 不需要改业务代码。
    """

    def __init__(self, keys: list[bytes]) -> None:
        if not keys:
            raise ValueError("FernetCipher 需要至少一个密钥")
        self._cipher = MultiFernet([Fernet(k) for k in keys])

    def encrypt(self, plaintext: str) -> str:
        """加密 UTF-8 字符串,返回 base64 url-safe token。"""
        token = self._cipher.encrypt(plaintext.encode("utf-8"))
        return token.decode("ascii")

    def decrypt(self, token: str) -> str:
        """解密 token,返回 UTF-8 字符串。"""
        plain = self._cipher.decrypt(token.encode("ascii"))
        return plain.decode("utf-8")

    def encrypt_dict(self, data: dict) -> str:
        """JSON 序列化(sort_keys 保稳)后加密。"""
        # sort_keys=True:确保相同 dict 总是产生相同的中间字符串(便于将来对比)
        # ensure_ascii=False:中文字段不转义,体积更小
        payload = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return self.encrypt(payload)

    def decrypt_dict(self, token: str) -> dict:
        """解密 + JSON 反序列化。"""
        payload = self.decrypt(token)
        decoded = json.loads(payload)
        if not isinstance(decoded, dict):
            raise ValueError("解密后内容不是 dict")
        return decoded


_cipher_singleton: FernetCipher | None = None


def get_cipher() -> FernetCipher:
    """单例,首次调用从 settings 读取 key 路径并初始化。"""
    global _cipher_singleton
    if _cipher_singleton is None:
        settings = get_settings()
        key = load_or_create_key(settings.encryption_key_path)
        _cipher_singleton = FernetCipher([key])
    return _cipher_singleton


def reset_cipher() -> None:
    """单元测试用:清空单例,允许下次 `get_cipher()` 重新加载。"""
    global _cipher_singleton
    _cipher_singleton = None
