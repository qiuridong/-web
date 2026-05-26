"""脚本上传 + 在线编辑 API(MVP-5)。

详见 ``进度/设计/Web脚本编辑器.md`` § 2。

5 个端点(都在 ``/scripts`` 前缀下,与既有 ``scripts.py`` router 共享 prefix):
- POST   /scripts/upload                🔒 上传 zip 或 multipart
- GET    /scripts/{slug}/files          🔒 列文件
- GET    /scripts/{slug}/files/{path}   🔒 读单文件文本
- PUT    /scripts/{slug}/files/{path}   🔒 写单文件 + dry-run
- (DELETE /scripts/{slug}?delete_files=true 见 ``scripts.py`` 增强)

所有端点 ``Depends(get_current_user)``;单用户场景下等价 admin。
异常用既有 ``app.core.exceptions.*`` 体系,error_handler 中间件统一格式化。
"""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, File, Query, Request, UploadFile, status
from fastapi.responses import PlainTextResponse
from loguru import logger
from sqlalchemy import select

from app.config import get_settings
from app.core.exceptions import (
    PayloadTooLarge,
    ValidationError,
)
from app.db.models.node import Node
from app.deps import CurrentUser, DBSession
from app.schemas.script_upload import (
    FileListResponse,
    FileReadResponse,
    FileWriteResponse,
    UploadResponse,
)
from app.services import script_service, script_upload_service

router = APIRouter(prefix="/scripts", tags=["scripts-upload"])


# ============================================================
# Upload
# ============================================================
@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_200_OK,
    summary="上传脚本(zip 或 multipart 多文件)",
)
async def upload_script(
    request: Request,
    db: DBSession,
    _user: CurrentUser,
    slug: Annotated[
        str | None,
        Query(
            description="目标 slug(留空则用 manifest.slug)",
            min_length=1,
            max_length=64,
        ),
    ] = None,
    force: Annotated[
        bool,
        Query(description="目标 slug 已存在时强制覆盖"),
    ] = False,
    dry_run: Annotated[
        bool,
        Query(description="是否上传前跑 dry-run(默认 true,推荐)"),
    ] = True,
    sync_to_nodes: Annotated[
        str | None,
        Query(
            description=(
                "MVP-2 推送同步:上传成功后立即把脚本推送到这些节点(逗号分隔 node_id,"
                "如 '2,3')。仅 enabled 且非 local 的节点生效。"
                "Agent 下次 poll(最长 30s)会自动 pull bundle.zip 并解压。"
            ),
            max_length=512,
        ),
    ] = None,
    files: Annotated[
        list[UploadFile] | None,
        File(description="multipart 多文件;与 application/zip 二选一"),
    ] = None,
) -> UploadResponse:
    """🔒 上传脚本目录。

    支持两种 ``Content-Type``:
    1. ``application/zip``  — 整 zip 上传(推荐)
    2. ``multipart/form-data`` — 多文件 ``files`` 字段

    流程:
    1. 校验 slug(若指定);保留字 / 正则
    2. 接收数据 → tmp 解压(zip)或落盘(multipart)
    3. 校验目录结构(必须有 manifest.yaml + schema 通过)
    4. 用 manifest.slug 校准最终 slug
    5. (可选)dry-run
    6. 原子 ``os.replace`` 到 ``scripts/<slug>/``
    7. 调 ``script_service.scan_all`` 入库
    """
    settings = get_settings()
    scripts_root = settings.scripts_dir.resolve()
    scripts_root.mkdir(parents=True, exist_ok=True)

    # 提前校验 slug 提示(若指定)
    if slug is not None:
        script_upload_service.validate_slug(slug)

    content_type = (request.headers.get("content-type") or "").lower()

    # 用唯一 tmp 目录隔离本次上传(scripts/.tmp-<uuid>/)
    # 关键:tmp 必须与 scripts_root 同盘,os.replace 才能跨原子
    tmp_parent = scripts_root / f".tmp-upload-{_short_uuid()}"
    tmp_parent.mkdir(parents=True, exist_ok=True)
    tmp_extract = tmp_parent / "_extract"
    tmp_extract.mkdir()

    try:
        # ===== 1. 接收数据 =====
        if "application/zip" in content_type or "application/x-zip-compressed" in content_type:
            # 直接读 body 字节
            raw = await request.body()
            if not raw:
                raise ValidationError(
                    "上传 body 为空",
                    details={"content_type": content_type},
                )
            if len(raw) > script_upload_service.MAX_ZIP_TOTAL_BYTES:
                raise PayloadTooLarge(
                    f"zip 大小 {len(raw)} > 上限 {script_upload_service.MAX_ZIP_TOTAL_BYTES}",
                    details={
                        "size": len(raw),
                        "limit": script_upload_service.MAX_ZIP_TOTAL_BYTES,
                    },
                )

            # 落到 tmp_parent/upload.zip 用 ZipFile 处理
            zip_path = tmp_parent / "upload.zip"
            zip_path.write_bytes(raw)

            # 安全校验 + 解压(extract_zip_to_tmp 内部会再校验一次)
            script_upload_service.extract_zip_to_tmp(zip_path, tmp_extract)

        elif files is not None and len(files) > 0:
            # multipart 多文件
            total = 0
            for f in files:
                if not f.filename:
                    continue
                # 路径安全:filename 不能含 / 或 ..
                filename = f.filename
                if "/" in filename or "\\" in filename or filename.startswith("."):
                    raise ValidationError(
                        f"multipart 文件名不合法: {filename!r}"
                        "(不允许含 / \\ 或以 . 开头)",
                        details={"filename": filename},
                    )

                data = await f.read()
                if len(data) > script_upload_service.MAX_FILE_BYTES:
                    raise PayloadTooLarge(
                        f"文件 {filename!r} 大小 {len(data)} > 上限 "
                        f"{script_upload_service.MAX_FILE_BYTES}",
                        details={
                            "filename": filename,
                            "size": len(data),
                            "limit": script_upload_service.MAX_FILE_BYTES,
                        },
                    )
                total += len(data)
                if total > script_upload_service.MAX_ZIP_TOTAL_BYTES:
                    raise PayloadTooLarge(
                        f"上传总大小 {total} > 上限 "
                        f"{script_upload_service.MAX_ZIP_TOTAL_BYTES}",
                        details={
                            "size": total,
                            "limit": script_upload_service.MAX_ZIP_TOTAL_BYTES,
                        },
                    )
                (tmp_extract / filename).write_bytes(data)

            if total == 0:
                raise ValidationError(
                    "未收到任何文件",
                    details={"content_type": content_type},
                )
        else:
            raise ValidationError(
                "Content-Type 必须为 application/zip 或 multipart/form-data",
                details={"content_type": content_type},
            )

        # ===== 2. 校验目录结构 =====
        validated = script_upload_service.validate_script_dir(tmp_extract)
        manifest_slug = validated["slug"]

        # 最终 slug:query 优先 → 未指定时用 manifest
        final_slug = slug or manifest_slug
        script_upload_service.validate_slug(final_slug)

        # 与 manifest slug 不一致时要修 manifest(scanner.py 严格要求 slug == dir name)
        # 简单策略:若 query slug != manifest slug,直接拒(避免用户混淆)
        if final_slug != manifest_slug:
            raise ValidationError(
                f"query 指定的 slug={final_slug!r} 与 manifest.slug={manifest_slug!r} 不一致;"
                "请保持一致或不传 query slug",
                details={
                    "query_slug": final_slug,
                    "manifest_slug": manifest_slug,
                },
            )

        # ===== 3. dry-run(可选) =====
        dry_run_result = None
        if dry_run:
            if not validated["has_main_py"]:
                raise ValidationError(
                    "缺少 main.py,无法 dry-run;若仅上传 manifest 请设 ?dry_run=false",
                    details={"slug": final_slug},
                )
            dry_run_result = script_upload_service.dry_run_script(tmp_extract)
            if not dry_run_result.passed:
                raise ValidationError(
                    f"dry-run 失败 exit_code={dry_run_result.exit_code} "
                    f"timed_out={dry_run_result.timed_out}",
                    details={
                        "exit_code": dry_run_result.exit_code,
                        "stdout_excerpt": dry_run_result.stdout_excerpt[-2048:],
                        "stderr_excerpt": dry_run_result.stderr_excerpt[-2048:],
                        "timed_out": dry_run_result.timed_out,
                        "duration_ms": dry_run_result.duration_ms,
                    },
                )

        # ===== 4. 原子落盘 =====
        files_written = script_upload_service.commit_to_scripts(
            tmp_extract,
            scripts_root,
            final_slug,
            force=force,
        )
        # tmp_extract 已被 os.replace 搬走,后面 finally 只需清 tmp_parent

        # ===== 5. 调 scan_all 入库 =====
        scan_result = script_service.scan_all(db, scripts_root)
        db.commit()

        # 拿入库的 script_record(供前端跳详情)
        script_record_dict: dict[str, Any] | None = None
        try:
            detail = script_service.get_script_detail(db, final_slug)
            # detail 是 dict;直接放进响应即可(前端自己消费)
            # 但 datetime 字段需要序列化:Pydantic 在 response_model 里会处理
            script_record_dict = {
                "id": detail["id"],
                "slug": detail["slug"],
                "name": detail["name"],
                "version": detail["version"],
                "enabled": detail["enabled"],
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "upload 入库后取 detail 失败(scan_all 应已入库) slug={} err={}",
                final_slug,
                exc,
            )

        # 计算文件总大小(供响应 total_bytes)
        target_dir = scripts_root / final_slug
        total_bytes = sum(
            p.stat().st_size for p in target_dir.rglob("*") if p.is_file()
        )

        # MVP-2 推送同步:把 slug 加到选定节点的 pending_actions.sync
        sync_requested_node_ids: list[int] = []
        if sync_to_nodes:
            sync_requested_node_ids = _request_node_sync(
                db, final_slug, sync_to_nodes
            )
            if sync_requested_node_ids:
                db.commit()
                logger.info(
                    "推送同步排队 slug={} → nodes={}",
                    final_slug, sync_requested_node_ids,
                )

        logger.info(
            "脚本上传成功 slug={} files={} total_bytes={} dry_run={} scan_added={} sync_to_nodes={}",
            final_slug,
            len(files_written),
            total_bytes,
            bool(dry_run_result),
            scan_result.get("added"),
            sync_requested_node_ids,
        )

        return UploadResponse(
            slug=final_slug,
            saved_path=f"scripts/{final_slug}/",
            files_written=files_written,
            total_bytes=total_bytes,
            dry_run=dry_run_result,
            script_record=script_record_dict,
            sync_requested_node_ids=sync_requested_node_ids,
        )

    finally:
        # 清 tmp_parent(成功:仅 zip 文件 + 空 _extract;失败:可能含部分文件)
        try:
            if tmp_parent.exists():
                shutil.rmtree(tmp_parent, ignore_errors=True)
        except Exception:  # noqa: BLE001
            logger.exception("清理 tmp_parent 失败 path={}", tmp_parent)


# ============================================================
# GET files
# ============================================================
@router.get(
    "/{slug}/files",
    response_model=FileListResponse,
    summary="列出脚本目录下所有文件",
)
def list_script_files(
    slug: str,
    _user: CurrentUser,
) -> FileListResponse:
    """🔒 列文件 + size / mtime / editable 标签。"""
    settings = get_settings()
    items = script_upload_service.list_files_in_script(
        settings.scripts_dir.resolve(), slug
    )
    return FileListResponse(files=items)


# ============================================================
# GET single file text
# ============================================================
@router.get(
    "/{slug}/files/{path:path}",
    response_model=FileReadResponse,
    summary="读单文件文本内容(JSON 包装)",
)
def read_script_file(
    slug: str,
    path: str,
    _user: CurrentUser,
) -> FileReadResponse:
    """🔒 读单文件;返回 JSON ``{path, size, mtime, content}``。

    二进制 / 超大 / .pyc 等抛 422 / 413。
    """
    settings = get_settings()
    content, size, mtime = script_upload_service.read_file_text(
        settings.scripts_dir.resolve(), slug, path
    )
    return FileReadResponse(path=path, size=size, mtime=mtime, content=content)


# ============================================================
# PUT single file text
# ============================================================
@router.put(
    "/{slug}/files/{path:path}",
    response_model=FileWriteResponse,
    summary="写单文件 + 自动 dry-run + 备份旧版到 .backups/",
)
async def write_script_file(
    request: Request,
    slug: str,
    path: str,
    db: DBSession,
    _user: CurrentUser,
    skip_dry_run: Annotated[
        bool,
        Query(
            description="跳过 dry-run(危险!默认 False)",
        ),
    ] = False,
) -> FileWriteResponse:
    """🔒 写单文件文本(``text/plain; charset=utf-8`` body)。

    流程:
    1. 路径 + 大小校验
    2. dry-run(除非 skip_dry_run=true)
    3. 备份旧版到 ``<slug>/.backups/<filename>.<ISO>.bak``
    4. 原子 ``os.replace`` 写新内容
    5. 触发 scan_all(若 manifest 改了 scan 会重读)
    """
    # body 可能是 text/plain 或 application/octet-stream;统一当 utf-8 解码
    raw = await request.body()
    if len(raw) > script_upload_service.MAX_FILE_BYTES:
        raise PayloadTooLarge(
            f"PUT body 大小 {len(raw)} > 上限 "
            f"{script_upload_service.MAX_FILE_BYTES}",
            details={
                "size": len(raw),
                "limit": script_upload_service.MAX_FILE_BYTES,
            },
        )

    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError(
            f"PUT body 不是合法 UTF-8: {exc}",
            details={"slug": slug, "path": path},
        ) from exc

    settings = get_settings()
    backup_rel, dry_run_result = script_upload_service.write_file_text(
        settings.scripts_dir.resolve(),
        slug,
        path,
        content,
        skip_dry_run=skip_dry_run,
    )

    if backup_rel is None and dry_run_result is not None and not dry_run_result.passed:
        # dry-run 失败,文件未落盘 → 422
        raise ValidationError(
            f"dry-run 失败,文件未保存 exit_code={dry_run_result.exit_code} "
            f"timed_out={dry_run_result.timed_out}",
            details={
                "exit_code": dry_run_result.exit_code,
                "stdout_excerpt": dry_run_result.stdout_excerpt[-2048:],
                "stderr_excerpt": dry_run_result.stderr_excerpt[-2048:],
                "timed_out": dry_run_result.timed_out,
                "duration_ms": dry_run_result.duration_ms,
            },
        )

    # 若改的是 manifest.yaml,触发 scan_all 让 DB 同步
    if path.endswith("manifest.yaml") or path.endswith("manifest.yml"):
        try:
            script_service.scan_all(db, settings.scripts_dir.resolve())
            db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "PUT manifest 后 scan_all 失败 slug={} err={}", slug, exc
            )

    return FileWriteResponse(
        saved=True,
        path=path,
        backup_path=backup_rel,
        dry_run=dry_run_result,
    )


# ============================================================
# 内部工具
# ============================================================
def _short_uuid() -> str:
    """8 字符随机后缀(供 tmp 目录命名)。"""
    import uuid  # 局部 import 避免污染模块
    return uuid.uuid4().hex[:8]


def _parse_node_ids(raw: str) -> list[int]:
    """解析 query 里的逗号分隔 node_id,失败的项跳过。"""
    out: list[int] = []
    for piece in raw.split(","):
        piece = piece.strip()
        if not piece:
            continue
        try:
            nid = int(piece)
        except ValueError:
            continue
        if nid > 0 and nid not in out:
            out.append(nid)
    return out


def _request_node_sync(
    db,
    slug: str,
    sync_to_nodes_raw: str,
) -> list[int]:
    """把 ``slug`` append 到选定节点的 ``pending_actions.sync`` 列表。

    过滤规则:
    - 必须 enabled
    - 必须非 ``is_local``(local 节点就是源,不需要同步)
    - 重复的 slug 在 sync 列表里去重

    :returns: 实际加入推送队列的 node_id 列表(过滤后)
    """
    requested_ids = _parse_node_ids(sync_to_nodes_raw)
    if not requested_ids:
        return []

    # 查 nodes,过滤 enabled + 非 local
    nodes = (
        db.scalars(
            select(Node).where(
                Node.id.in_(requested_ids),
                Node.enabled.is_(True),
                Node.is_local.is_(False),
            )
        ).all()
    )

    accepted: list[int] = []
    for node in nodes:
        # 解析现有 pending_actions
        try:
            current = json.loads(node.pending_actions or "{}")
            if not isinstance(current, dict):
                current = {}
        except (json.JSONDecodeError, TypeError, ValueError):
            current = {}

        sync_list = [str(s) for s in current.get("sync", []) if isinstance(s, str)]
        delete_list = [
            str(s) for s in current.get("delete", []) if isinstance(s, str)
        ]

        # 去重 append
        if slug not in sync_list:
            sync_list.append(slug)

        node.pending_actions = json.dumps(
            {"sync": sync_list, "delete": delete_list},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        accepted.append(node.id)

    return accepted
