"""临时 wrapper:绕过 alembic 在 Windows 中文路径下的 UTF-8 / GBK 编码问题。

Alembic 内部用 `encoding="locale"` 读 `alembic.ini`(见
`alembic/util/compat.py::read_config_parser`),Python 3.12 在 Windows 上把
locale 解析为 GBK,而 `alembic.ini` 是 UTF-8 编码,导致 `UnicodeDecodeError`。

本脚本在调用 alembic CLI 前 monkey-patch `read_config_parser` 强制 UTF-8。
首次成功生成 0001_initial 迁移后即可删除本文件。
"""
from __future__ import annotations

import sys

from alembic.util import compat as _alembic_compat
from configparser import RawConfigParser


def _read_config_parser_utf8(file_config: RawConfigParser, file_argument: str | list[str]) -> list[str]:
    """强制以 UTF-8 读取 alembic.ini,避免 Windows 中文路径下的 locale=cp936 解码失败。"""
    return file_config.read(file_argument, encoding="utf-8")


_alembic_compat.read_config_parser = _read_config_parser_utf8


from alembic.config import CommandLine  # noqa: E402

if __name__ == "__main__":
    CommandLine(prog="alembic").main(argv=sys.argv[1:])
