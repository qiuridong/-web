"""脚本路由：读公开（列表/详情/bundle.zip/icon/文件）+ 写鉴权（上传/编辑/删除/标签）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.core.exceptions import PayloadTooLarge, ScriptNotFound, ValidationError
from app.db.models.user import User
from app.deps import get_db, require_user
from app.schemas.script import (
    FileContentResponse,
    FileItem,
    FileListResponse,
    ScriptDetail,
    ScriptListItem,
    UpdateScriptRequest,
    UploadResponse,
    WriteFileRequest,
    detail_from_row,
    list_item_from_row,
)
from app.services import script_store

router = APIRouter(prefix="/scripts", tags=["scripts"])

_MAX_UPLOAD_BYTES = 4 * 1024 * 1024


async def _read_zip_bytes(request: Request, file: UploadFile | None) -> bytes:
    data = await file.read() if file is not None else await request.body()
    if not data:
        raise ValidationError("未收到 zip 数据（请上传 .zip 文件或以 application/zip 提交）")
    if len(data) > _MAX_UPLOAD_BYTES:
        raise PayloadTooLarge("上传体过大", details={"size": len(data), "limit": _MAX_UPLOAD_BYTES})
    return data


# ============================================================
# 读（公开）
# ============================================================
@router.get("", response_model=list[ScriptListItem])
def list_scripts(db: Session = Depends(get_db)) -> list[ScriptListItem]:
    return [list_item_from_row(r) for r in script_store.list_scripts(db)]


@router.get("/{slug}", response_model=ScriptDetail)
def get_detail(slug: str, db: Session = Depends(get_db)) -> ScriptDetail:
    return detail_from_row(script_store.get_script(db, slug))


@router.get("/{slug}/bundle.zip")
def download_bundle(slug: str, db: Session = Depends(get_db)) -> Response:
    data = script_store.bundle_zip(db, slug)
    db.commit()
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{slug}.zip"'},
    )


@router.get("/{slug}/icon")
def get_icon(slug: str, db: Session = Depends(get_db)) -> Response:
    row = script_store.get_script(db, slug)
    if not row.icon_svg:
        raise ScriptNotFound("该脚本无图标", details={"slug": slug})
    return Response(
        content=row.icon_svg,
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=300"},
    )


@router.get("/{slug}/files", response_model=FileListResponse)
def list_files(slug: str, db: Session = Depends(get_db)) -> FileListResponse:
    script_store.get_script(db, slug)  # 404 校验
    files = [FileItem(**f) for f in script_store.list_files(slug)]
    return FileListResponse(slug=slug, files=files)


@router.get("/{slug}/files/{path:path}", response_model=FileContentResponse)
def read_file(slug: str, path: str, db: Session = Depends(get_db)) -> FileContentResponse:
    script_store.get_script(db, slug)  # 404 校验
    return FileContentResponse(slug=slug, path=path, content=script_store.read_file(slug, path))


# ============================================================
# 写（鉴权）
# ============================================================
@router.post("/upload", response_model=UploadResponse)
async def upload_script(
    request: Request,
    force: bool = False,
    file: UploadFile | None = File(default=None),
    _user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> UploadResponse:
    data = await _read_zip_bytes(request, file)
    row, created = script_store.import_from_zip(db, data, force=force)
    db.commit()
    return UploadResponse(slug=row.slug, name=row.name, version=row.version, created=created)


@router.put("/{slug}/files/{path:path}", response_model=ScriptDetail)
def write_file(
    slug: str,
    path: str,
    payload: WriteFileRequest,
    _user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> ScriptDetail:
    row = script_store.write_file(db, slug, path, payload.content)
    db.commit()
    return detail_from_row(row)


@router.patch("/{slug}", response_model=ScriptDetail)
def update_script(
    slug: str,
    payload: UpdateScriptRequest,
    _user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> ScriptDetail:
    row = script_store.get_script(db, slug)
    if payload.category is not None:
        row.category = payload.category.strip() or None
    if payload.tags is not None:
        row.tags = payload.tags
    db.flush()
    db.commit()
    return detail_from_row(row)


@router.delete("/{slug}", status_code=status.HTTP_204_NO_CONTENT)
def delete_script(
    slug: str,
    _user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> None:
    script_store.delete_script(db, slug)
    db.commit()
