"""全局设置 API — `/api/v1/settings/*`。

实现见 `进度/设计/后端架构.md` § 2.6 + § 9.3。

端点清单
--------
- ``GET    /settings``                       🔒 全部 KV(is_secret 项 value=null)
- ``GET    /settings/{key}``                 🔒 单项
- ``PUT    /settings/{key}``                 🔒 严格白名单 key 校验
- ``POST   /settings/backup/export``         🔒 流式 zip 下载
- ``POST   /settings/backup/import``         🔒 multipart upload(v1 仅解析 meta)
"""
from __future__ import annotations

import io
import json
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import APIRouter, File, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import ValidationError as PydanticValidationError

from app.config import get_settings
from app.core.exceptions import ValidationError
from app.db.models.setting import Setting
from app.deps import CurrentUser, DBSession
from app.schemas.setting import (
    BackupExportMeta,
    BackupImportResponse,
    SettingItem,
    SettingListResponse,
    SettingUpdateRequest,
)
from app.services import settings_service

router = APIRouter(prefix="/settings", tags=["settings"])


# ============================================================
# 内部:ORM → schema dict(脱敏)
# ============================================================
def _row_to_item_dict(
    row: Any,
    *,
    cached_value: Any | None = None,
) -> dict[str, Any]:
    """把 Setting ORM 行(或 (key, value, ...))转 dict;is_secret 项 value=None。

    ``cached_value``:若已解码就直接传入,避免再次 json.loads。
    """
    key = row.key
    if cached_value is not None:
        value = cached_value
    else:
        try:
            value = json.loads(row.value_json) if row.value_json else None
        except json.JSONDecodeError:
            value = None
    if row.is_secret:
        value = None
    return {
        "key": key,
        "value": value,
        "description": row.description,
        "is_secret": bool(row.is_secret),
        "updated_at": row.updated_at,
        "updated_by": row.updated_by,
    }


# ============================================================
# 列表
# ============================================================
@router.get(
    "",
    response_model=SettingListResponse,
    summary="全部 setting(is_secret 项 value 脱敏为 null)",
)
def list_settings(
    db: DBSession,
    _user: CurrentUser,
) -> SettingListResponse:
    """🔒 凡 ``ALLOWED_KEYS`` 内的项都会出现,即便 DB 还没插过默认值。"""
    # 把现有行做 dict
    rows = settings_service.list_all(db)
    by_key = {r.key: r for r in rows}

    items: list[SettingItem] = []
    for key in sorted(settings_service.ALLOWED_KEYS):
        row = by_key.get(key)
        meta = settings_service.DEFAULT_SETTINGS[key]
        if row is not None:
            items.append(SettingItem.model_validate(_row_to_item_dict(row)))
        else:
            # 尚未 ensure_defaults 时的兜底
            value = (
                None
                if meta.get("is_secret")
                else meta["default"]
            )
            items.append(
                SettingItem(
                    key=key,
                    value=value,
                    description=meta.get("description"),
                    is_secret=bool(meta.get("is_secret", False)),
                    updated_at=None,
                    updated_by=None,
                )
            )

    # 把数据库里有但不在白名单的项也展示(只读 — 用于诊断历史脏数据)
    for key, row in by_key.items():
        if key not in settings_service.ALLOWED_KEYS:
            items.append(SettingItem.model_validate(_row_to_item_dict(row)))

    return SettingListResponse(items=items)


# ============================================================
# 备份导出/导入(必须放在 /{key} 之前)
# ============================================================
@router.post(
    "/backup/export",
    summary="导出全量备份(zip:db.sqlite3 + meta.json + 可选 encryption.key)",
)
def backup_export(
    _user: CurrentUser,
    include_key: Annotated[
        bool,
        Query(
            description="是否在 zip 中包含 encryption.key(危险!默认 false)",
        ),
    ] = False,
) -> StreamingResponse:
    """🔒 把 db.sqlite3 + meta.json (+ encryption.key) 打成 zip 流式下载。

    数据库一致性:用 sqlite3 内置 ``.backup`` 接口做在线快照(WAL 安全)。
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)
    filename = f"checkin-panel-backup-{now.strftime('%Y%m%d-%H%M%S')}.zip"

    db_path = _resolve_sqlite_path(settings.database_url)
    if db_path is None or not db_path.exists():
        raise ValidationError(
            "当前数据库不是 SQLite 或文件不存在,无法导出",
            details={"database_url": settings.database_url},
        )

    # 1) 一致性快照到临时文件
    tmp_dir = Path(tempfile.mkdtemp(prefix="checkin-backup-"))
    snapshot_path = tmp_dir / "db.sqlite3"
    try:
        _sqlite_online_backup(db_path, snapshot_path)
    except Exception as exc:  # noqa: BLE001
        logger.exception("sqlite 在线备份失败 err={}", exc)
        # 兜底:直接拷文件(可能不一致但总比没有强)
        snapshot_path.write_bytes(db_path.read_bytes())

    # 2) 构造 meta
    meta = BackupExportMeta(
        version="0.1.0",
        exported_at=now,
        includes_key=bool(include_key),
        schema_version=1,
    )

    # 3) 打 zip
    buf = io.BytesIO()
    with ZipFile(buf, "w", compression=ZIP_DEFLATED) as zf:
        zf.write(snapshot_path, arcname="db.sqlite3")
        zf.writestr(
            "meta.json",
            json.dumps(meta.model_dump(mode="json"), ensure_ascii=False, indent=2),
        )
        if include_key:
            key_path = settings.encryption_key_path
            if key_path.exists():
                zf.write(key_path, arcname="encryption.key")
            else:
                logger.warning(
                    "include_key=true 但 key 文件不存在 path={}", key_path
                )

    # 4) 清理临时
    try:
        snapshot_path.unlink(missing_ok=True)
        tmp_dir.rmdir()
    except OSError:  # pragma: no cover
        pass

    buf.seek(0)
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "no-store",
    }
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="application/zip",
        headers=headers,
    )


def _resolve_sqlite_path(database_url: str) -> Path | None:
    """从 ``sqlite:///./data/db.sqlite3`` 解出文件路径。"""
    if not database_url.startswith("sqlite"):
        return None
    # 形式:sqlite:///absolute  或  sqlite:///relative
    # SQLAlchemy 用 4 斜杠表示绝对路径(sqlite:////tmp/x)
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        # 例如 sqlite:////absolute
        if database_url.startswith("sqlite:////"):
            return Path(database_url[len("sqlite:////") - 1 :])
        return None
    rest = database_url[len(prefix) :]
    return Path(rest)


def _sqlite_online_backup(src_path: Path, dst_path: Path) -> None:
    """用 sqlite3 内建 ``.backup`` 做一致性快照(无视 WAL 状态)。"""
    src = sqlite3.connect(str(src_path))
    try:
        dst = sqlite3.connect(str(dst_path))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


@router.post(
    "/backup/import",
    response_model=BackupImportResponse,
    status_code=status.HTTP_200_OK,
    summary="导入 zip 备份(v1 简化:仅解析 meta,真替换需外部重启)",
)
async def backup_import(
    _user: CurrentUser,
    file: Annotated[UploadFile, File(description="备份 zip 文件")],
) -> BackupImportResponse:
    """🔒 接受 multipart upload 的 zip,解析其中 ``meta.json``。

    v1 暂不自动替换 + 重启;只校验 zip 结构 + 返回 meta + TODO 提示。
    真正的还原:需要运维人员手动 stop 服务、替换 ``data/db.sqlite3``
    与可选 ``data/encryption.key``,然后 ``docker compose restart``。
    """
    raw = await file.read()
    if not raw:
        raise ValidationError("上传文件为空", details={"filename": file.filename})

    try:
        with ZipFile(io.BytesIO(raw)) as zf:
            names = set(zf.namelist())
            if "meta.json" not in names:
                raise ValidationError(
                    "zip 中缺少 meta.json,不是合法备份",
                    details={"namelist": sorted(names)},
                )
            if "db.sqlite3" not in names:
                raise ValidationError(
                    "zip 中缺少 db.sqlite3,不是合法备份",
                    details={"namelist": sorted(names)},
                )
            meta_raw = zf.read("meta.json").decode("utf-8")
    except ValidationError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ValidationError(
            f"无法解析 zip: {exc}",
            details={"filename": file.filename},
        ) from exc

    try:
        meta_dict = json.loads(meta_raw)
        parsed = BackupExportMeta.model_validate(meta_dict)
    except (json.JSONDecodeError, PydanticValidationError) as exc:
        raise ValidationError(
            f"meta.json 格式不合法: {exc}",
            details={"filename": file.filename},
        ) from exc

    logger.info(
        "收到备份导入 meta version={} exported_at={} includes_key={}",
        parsed.version,
        parsed.exported_at,
        parsed.includes_key,
    )
    return BackupImportResponse(
        parsed=parsed,
        message=(
            "v1 暂不自动替换数据库与密钥。"
            "请运维手动停服 → 替换 data/db.sqlite3 与可选 data/encryption.key → "
            "执行 docker compose restart。"
        ),
    )


# ============================================================
# 单项(必须放在备份端点之后)
# ============================================================
@router.get(
    "/{key}",
    response_model=SettingItem,
    summary="单项(is_secret 项 value 脱敏)",
)
def get_setting(
    key: str,
    db: DBSession,
    _user: CurrentUser,
) -> SettingItem:
    """🔒 单项读取。

    若不在白名单 → 404(走 ValidationError 422?用 ValidationError 更对应 — 不存在的 key)
    若 DB 没记录 → 返回默认值。
    """
    if key not in settings_service.ALLOWED_KEYS:
        raise ValidationError(
            f"未知 setting key: {key!r}",
            details={"key": key, "allowed": sorted(settings_service.ALLOWED_KEYS)},
        )

    row = db.get(Setting, key)
    if row is not None:
        return SettingItem.model_validate(_row_to_item_dict(row))

    meta = settings_service.DEFAULT_SETTINGS[key]
    return SettingItem(
        key=key,
        value=None if meta.get("is_secret") else meta["default"],
        description=meta.get("description"),
        is_secret=bool(meta.get("is_secret", False)),
        updated_at=None,
        updated_by=None,
    )


@router.put(
    "/{key}",
    response_model=SettingItem,
    summary="更新单项(白名单校验)",
)
def update_setting(
    key: str,
    payload: SettingUpdateRequest,
    db: DBSession,
    current_user: CurrentUser,
) -> SettingItem:
    """🔒 PUT,key 必须在白名单。

    set 内部会做类型与范围校验,失败抛 422(ValidationError)。
    成功后清缓存。
    """
    user_id: int | None = getattr(current_user, "id", None)
    row = settings_service.set_value(
        db,
        key=key,
        value=payload.value,
        user_id=user_id,
    )
    db.commit()
    db.refresh(row)
    return SettingItem.model_validate(_row_to_item_dict(row))


