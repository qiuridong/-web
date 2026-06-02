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
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, File, Query, Request, UploadFile, status
from fastapi.responses import PlainTextResponse
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.exceptions import (
    ExternalServiceError,
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

        # ===== 2~5. 校验目录 → dry-run → 原子落盘 → 入库 → 构造响应 =====
        # 这段流程与 ``upload-from-url`` 端点完全一致,抽成 _finalize_ingest 复用
        # (service 层零改;两个端点只是"把 zip 字节弄进 tmp_extract"的来源不同)。
        return _finalize_ingest(
            db,
            scripts_root,
            tmp_extract,
            slug=slug,
            force=force,
            dry_run=dry_run,
            sync_to_nodes=sync_to_nodes,
        )

    finally:
        # 清 tmp_parent(成功:仅 zip 文件 + 空 _extract;失败:可能含部分文件)
        try:
            if tmp_parent.exists():
                shutil.rmtree(tmp_parent, ignore_errors=True)
        except Exception:  # noqa: BLE001
            logger.exception("清理 tmp_parent 失败 path={}", tmp_parent)


# ============================================================
# Upload from URL(脚本货架对接 · M3)
# ============================================================
#: 远端 zip 下载体积上限(4 MiB)— 比单 zip 解压上限(1 MiB)宽松,
#: 给压缩比与传输头留余量;真正的脚本 bundle 通常 < 50 KB。
MAX_REMOTE_ZIP_BYTES: int = 4 * 1024 * 1024

#: 远端下载超时(秒)
REMOTE_DOWNLOAD_TIMEOUT_SEC: float = 30.0


@router.post(
    "/upload-from-url",
    response_model=UploadResponse,
    status_code=status.HTTP_200_OK,
    summary="从 URL 下载 zip 并入库(脚本货架「一键安装」/「导入」对接)",
)
async def upload_script_from_url(
    db: DBSession,
    _user: CurrentUser,
    zip_url: Annotated[
        str,
        Query(
            description=(
                "远端标准脚本 zip 的 URL(http/https)。下载后复用与 ``/upload`` "
                "完全相同的校验/落盘/入库流程。slug 始终取自 manifest.yaml。"
            ),
            min_length=1,
            max_length=2048,
        ),
    ],
    force: Annotated[
        bool,
        Query(description="目标 slug 已存在时强制覆盖"),
    ] = False,
    dry_run: Annotated[
        bool,
        Query(description="是否入库前跑 dry-run(默认 true,推荐)"),
    ] = True,
    sync_to_nodes: Annotated[
        str | None,
        Query(
            description=(
                "入库成功后立即把脚本推送到这些节点(逗号分隔 node_id)。"
                "语义与 ``/upload`` 的同名参数一致。"
            ),
            max_length=512,
        ),
    ] = None,
) -> UploadResponse:
    """🔒 从 URL 下载标准脚本 zip → 入库。

    用于「脚本货架」对接的两条路径:
    1. 管家「脚本市场」页点「安装」:``zip_url`` = 货架 ``/api/scripts/{slug}/bundle.zip``
    2. 货架「导入到管家」跳 ``/scripts?import=<bundle url>`` → 前端调本端点

    流程:
    1. 校验 ``zip_url`` scheme(仅 http/https)
    2. 用 httpx 流式下载,累计超过 :data:`MAX_REMOTE_ZIP_BYTES` 立即中止(413)
    3. 写 tmp → ``extract_zip_to_tmp`` → 复用 ``_finalize_ingest``(与 ``/upload`` 同一套)

    安全:本端点 ``Depends(get_current_user)``(仅已登录管理员可调),
    且只接受 http/https + 体积上限,下载体由后续 zip 安全链(zip slip / 单文件 /
    总大小 / manifest schema)兜底校验。
    """
    settings = get_settings()
    scripts_root = settings.scripts_dir.resolve()
    scripts_root.mkdir(parents=True, exist_ok=True)

    # ===== 1. 下载远端 zip 字节(scheme 校验 + 体积上限在内部) =====
    raw = await _download_zip_from_url(zip_url)

    # 用唯一 tmp 目录隔离本次上传(与 /upload 同盘,os.replace 才能原子)
    tmp_parent = scripts_root / f".tmp-upload-{_short_uuid()}"
    tmp_parent.mkdir(parents=True, exist_ok=True)
    tmp_extract = tmp_parent / "_extract"
    tmp_extract.mkdir()

    try:
        zip_path = tmp_parent / "upload.zip"
        zip_path.write_bytes(raw)

        # 安全校验 + 解压(extract_zip_to_tmp 内部再校验一次 zip slip / 大小)
        script_upload_service.extract_zip_to_tmp(zip_path, tmp_extract)

        # ===== 2~5. 复用与 /upload 完全相同的入库流程 =====
        # slug 不从 query 传(契约里 from-url 无 slug 参数)→ 始终用 manifest.slug
        return _finalize_ingest(
            db,
            scripts_root,
            tmp_extract,
            slug=None,
            force=force,
            dry_run=dry_run,
            sync_to_nodes=sync_to_nodes,
        )
    finally:
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
def _finalize_ingest(
    db: Session,
    scripts_root: Path,
    tmp_extract: Path,
    *,
    slug: str | None,
    force: bool,
    dry_run: bool,
    sync_to_nodes: str | None,
) -> UploadResponse:
    """把已解压到 ``tmp_extract`` 的脚本目录校验 → dry-run → 原子落盘 → 入库。

    ``/upload``(zip body / multipart)与 ``/upload-from-url``(远端下载)两个端点
    的公共后半段。**完全复用 service 层函数,service 零改**;此处只是把"数据进
    tmp_extract"之后的步骤抽出来共享,避免两份重复实现漂移。

    :param slug: query 指定的 slug(``/upload`` 可传;``upload-from-url`` 恒为 None
                 → 用 manifest.slug)。传入时必须与 manifest.slug 一致,否则 422。
    """
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
    # tmp_extract 已被 os.replace 搬走,调用方 finally 只需清 tmp_parent

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


async def _download_zip_from_url(zip_url: str) -> bytes:
    """下载远端 zip 字节,带 scheme 校验 + 体积上限 + 超时。

    - scheme 必须是 http/https,否则 422(``ValidationError``)
    - 流式累计,超过 :data:`MAX_REMOTE_ZIP_BYTES` 立即中止 → 413(``PayloadTooLarge``)
    - 远端非 200 / 网络错误 → 502(``ExternalServiceError``)

    :raises ValidationError: scheme/host 非法 or 空响应
    :raises PayloadTooLarge: 超体积上限
    :raises ExternalServiceError: 远端非 200 / 网络层错误
    """
    parsed = urlparse(zip_url)
    if parsed.scheme not in ("http", "https"):
        raise ValidationError(
            f"zip_url 协议必须是 http/https,收到 {parsed.scheme or '(空)'!r}",
            details={"zip_url": zip_url, "scheme": parsed.scheme},
        )
    if not parsed.netloc:
        raise ValidationError(
            "zip_url 缺少主机名",
            details={"zip_url": zip_url},
        )

    timeout = httpx.Timeout(REMOTE_DOWNLOAD_TIMEOUT_SEC)
    chunks: list[bytes] = []
    try:
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=timeout
        ) as client:
            async with client.stream(
                "GET",
                zip_url,
                headers={"Accept": "application/zip, application/octet-stream, */*"},
            ) as resp:
                if resp.status_code != 200:
                    raise ExternalServiceError(
                        f"下载 zip 失败:远端返回 HTTP {resp.status_code}",
                        details={"zip_url": zip_url, "status": resp.status_code},
                    )

                # Content-Length 快速预拒(若远端给了且超限)
                cl = resp.headers.get("content-length")
                if cl is not None:
                    try:
                        if int(cl) > MAX_REMOTE_ZIP_BYTES:
                            raise PayloadTooLarge(
                                f"远端 zip Content-Length {cl} > 上限 {MAX_REMOTE_ZIP_BYTES}",
                                details={
                                    "zip_url": zip_url,
                                    "content_length": int(cl),
                                    "limit": MAX_REMOTE_ZIP_BYTES,
                                },
                            )
                    except ValueError:
                        pass  # content-length 非数字,忽略,靠流式累计兜底

                total = 0
                async for chunk in resp.aiter_bytes():
                    total += len(chunk)
                    if total > MAX_REMOTE_ZIP_BYTES:
                        raise PayloadTooLarge(
                            f"远端 zip 下载超过上限 {MAX_REMOTE_ZIP_BYTES} 字节",
                            details={"zip_url": zip_url, "limit": MAX_REMOTE_ZIP_BYTES},
                        )
                    chunks.append(chunk)
    except (ValidationError, PayloadTooLarge, ExternalServiceError):
        raise
    except httpx.HTTPError as exc:
        raise ExternalServiceError(
            f"下载 zip 网络错误: {exc}",
            details={"zip_url": zip_url, "error": str(exc)},
        ) from exc

    raw = b"".join(chunks)
    if not raw:
        raise ValidationError(
            "下载的 zip 为空(0 字节)",
            details={"zip_url": zip_url},
        )
    logger.info("upload-from-url 下载完成 url={} size={}", zip_url, len(raw))
    return raw


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
