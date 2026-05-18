"""脚本上传 / 文件编辑 API schemas(MVP-5)。

详见 ``进度/设计/Web脚本编辑器.md`` § 2.2 + § 2.3。

模型清单
--------
- :class:`DryRunResult`     dry-run 子进程结果(stdout/stderr/exit_code/duration)
- :class:`UploadResponse`   ``POST /scripts/upload`` 响应
- :class:`FileListItem`     ``GET /scripts/{slug}/files`` 单项
- :class:`FileListResponse` ``GET /scripts/{slug}/files`` 完整响应
- :class:`FileReadResponse` ``GET /scripts/{slug}/files/{path}`` 响应(JSON 包装)
- :class:`FileWriteResponse``PUT /scripts/{slug}/files/{path}`` 响应
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ============================================================
# Dry-run 结果(供 upload + PUT 共用)
# ============================================================
class DryRunResult(BaseModel):
    """sandbox_runner 跑一次 dry-run 的产出。

    供 ``UploadResponse.dry_run_passed`` / ``FileWriteResponse.dry_run`` 引用。
    """

    model_config = ConfigDict(extra="ignore")

    passed: bool = Field(..., description="exit_code == 0 视为通过")
    exit_code: int = Field(..., description="子进程 exit code")
    duration_ms: int = Field(..., description="耗时毫秒")
    stdout_excerpt: str = Field(
        default="",
        description="stdout 截尾(最多 4 KiB,避免响应体膨胀)",
    )
    stderr_excerpt: str = Field(
        default="",
        description="stderr 截尾(最多 4 KiB)",
    )
    timed_out: bool = Field(default=False, description="是否超时被杀")


# ============================================================
# Upload(POST /scripts/upload)
# ============================================================
class UploadResponse(BaseModel):
    """上传成功响应。

    设计稿 § 2.2 响应 JSON。
    """

    model_config = ConfigDict(extra="ignore")

    slug: str = Field(..., description="入库 slug(与 manifest.slug + 目录名一致)")
    saved_path: str = Field(..., description="落盘相对路径,如 ``scripts/v2ex/``")
    files_written: list[str] = Field(
        default_factory=list,
        description="实际写入文件相对路径列表",
    )
    total_bytes: int = Field(..., description="所有写入文件总大小")
    dry_run: DryRunResult | None = Field(
        default=None,
        description="若开启 ``?dry_run=true`` 则为本次预跑结果;否则 null",
    )
    script_record: dict[str, Any] | None = Field(
        default=None,
        description=(
            "若 scan_all 成功 upsert,则为新脚本 ScriptDetail dict 形态。"
            "失败(例如 manifest 解析失败但 dry-run 通过)时为 null。"
        ),
    )


# ============================================================
# Files 列表(GET /scripts/{slug}/files)
# ============================================================
class FileListItem(BaseModel):
    """脚本目录下单个文件元信息。

    ``editable`` 判定见 ``script_upload_service.list_files_in_script``。
    """

    model_config = ConfigDict(extra="ignore")

    path: str = Field(..., description="相对脚本根目录的 POSIX 风格路径")
    size: int = Field(..., description="字节数")
    mtime: datetime = Field(..., description="UTC modification time")
    editable: bool = Field(
        ...,
        description=(
            "True = 文本可在线编辑;False = 二进制 / 超大 / 受保护"
            "(.pyc / .so / .exe / > 256 KiB / .backups/ 内)"
        ),
    )


class FileListResponse(BaseModel):
    """``GET /scripts/{slug}/files`` 完整响应。"""

    files: list[FileListItem] = Field(default_factory=list)


# ============================================================
# 单文件读
# ============================================================
class FileReadResponse(BaseModel):
    """``GET /scripts/{slug}/files/{path}`` JSON 包装形态。

    端点实际返回 ``text/plain``(便于前端 ``<textarea>``)
    与 ``application/json``(便于程序化消费)两种;
    后者用此 schema。
    """

    model_config = ConfigDict(extra="ignore")

    path: str
    size: int
    mtime: datetime
    content: str


# ============================================================
# 单文件写
# ============================================================
class FileWriteResponse(BaseModel):
    """``PUT /scripts/{slug}/files/{path}`` 响应。"""

    model_config = ConfigDict(extra="ignore")

    saved: bool = Field(..., description="是否真的落盘了(False = dry-run 失败)")
    path: str = Field(..., description="保存的文件相对路径")
    backup_path: str | None = Field(
        default=None,
        description="原文件备份路径(``.backups/<filename>.<ISO>.bak``),无备份时为 null",
    )
    dry_run: DryRunResult | None = Field(
        default=None,
        description="dry-run 结果;若 ``?skip_dry_run=true`` 则为 null",
    )
