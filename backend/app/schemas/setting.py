"""设置 schemas — Pydantic v2。

实现见 `进度/设计/后端架构.md` § 2.6 + § 1.8。

模型清单
--------
- ``SettingItem``                 单项(value 任意 JSON 类型;is_secret 项 value 脱敏为 None)
- ``SettingListResponse``         GET /settings 响应
- ``SettingUpdateRequest``        PUT /settings/{key} 请求
- ``BackupExportMeta``            导出 meta.json 内容
- ``BackupImportRequest``         POST /settings/backup/import 请求(multipart form 中文件名外的字段)
- ``BackupImportResponse``        导入响应(v1 暂只解析 meta)
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ============================================================
# 单项
# ============================================================
class SettingItem(BaseModel):
    """单个 setting。

    若 ``is_secret=True``,GET 响应里 ``value`` 始终为 ``None`` 并附 ``_secret_set: bool``。
    """

    model_config = ConfigDict(from_attributes=True)

    key: str = Field(..., max_length=64)
    value: Any = Field(
        default=None,
        description="JSON 值;is_secret 项 GET 时始终为 null",
    )
    description: str | None = None
    is_secret: bool = False
    updated_at: datetime | None = None
    updated_by: int | None = None


class SettingListResponse(BaseModel):
    """``GET /settings`` 响应。"""

    items: list[SettingItem]


# ============================================================
# Update
# ============================================================
class SettingUpdateRequest(BaseModel):
    """``PUT /settings/{key}`` 请求体。"""

    model_config = ConfigDict(extra="forbid")

    value: Any = Field(..., description="任意 JSON;由 service 层结合 key 类型校验")


# ============================================================
# Backup export / import
# ============================================================
class BackupExportMeta(BaseModel):
    """备份 zip 内的 meta.json。"""

    version: str
    exported_at: datetime
    includes_key: bool
    schema_version: int = 1


class BackupImportResponse(BaseModel):
    """``POST /settings/backup/import`` 响应。

    audit High #15:
    - HTTP 状态码改为 ``202 Accepted``(原 200 OK,用户以为已成功恢复)
    - ``message`` 文案以 ``[需要手动重启完成恢复]`` 开头,强调"未完成"
    - 新增 ``staging_dir`` 字段:文件落到磁盘的目录,运维直接 mv 即可
    """

    parsed: BackupExportMeta
    message: str = Field(
        ...,
        description=(
            "状态提示;v1 阶段以 [需要手动重启完成恢复] 开头,提示用户"
            "查看 staging_dir 中文件,完成 mv + restart"
        ),
    )
    staging_dir: str | None = Field(
        default=None,
        description=(
            "audit High #15:zip 解包后落到的 staging 目录绝对路径。"
            "运维需要把其中的 db.sqlite3 / encryption.key mv 到 data/ 并重启。"
        ),
    )
