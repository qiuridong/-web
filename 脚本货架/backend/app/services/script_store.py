"""货架脚本仓储 — 增删改查 + 从 zip/目录入库 + 在线编辑。

脚本源文件落在 ``settings.scripts_dir/<slug>/``（结构同管家 scripts/）；
``hub_scripts`` 表只存元数据。入库走与管家完全一致的 zip/manifest 校验口径，
确保产出 bundle 能被管家接受。
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.exceptions import (
    ConflictError,
    PayloadTooLarge,
    PermissionError,
    ScriptNotFound,
    ValidationError,
)
from app.db.models.script import HubScript
from app.services import bundle as bundle_svc
from app.services.manifest import parse_manifest, parse_manifest_text, summarize_fields


def _scripts_root() -> Path:
    root = Path(get_settings().scripts_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _extract_icon(target: Path, manifest) -> str | None:
    """读取 manifest.icon 指向的 svg 文件内容（内联存储，前端直接渲染）。"""
    icon_rel = getattr(manifest, "icon", "icon.svg") or "icon.svg"
    icon_path = target / icon_rel
    if icon_path.is_file() and icon_path.suffix.lower() == ".svg":
        try:
            text = icon_path.read_text(encoding="utf-8")
            return text[:50000]  # 防异常超大 svg
        except OSError:
            return None
    return None


# ============================================================
# 查询
# ============================================================
def list_scripts(db: Session) -> list[HubScript]:
    return list(
        db.execute(select(HubScript).order_by(HubScript.updated_at.desc())).scalars().all()
    )


def get_script(db: Session, slug: str) -> HubScript:
    row = db.execute(select(HubScript).where(HubScript.slug == slug)).scalar_one_or_none()
    if row is None:
        raise ScriptNotFound(f"脚本不存在: {slug}", details={"slug": slug})
    return row


# ============================================================
# 入库（共用 upsert）
# ============================================================
def _upsert_row(db: Session, slug: str, manifest, manifest_text: str, target: Path) -> tuple[HubScript, bool]:
    root = _scripts_root()
    _data, sha, size = bundle_svc.compute_script_bundle(root, slug)
    row = db.execute(select(HubScript).where(HubScript.slug == slug)).scalar_one_or_none()
    created = row is None
    if created:
        row = HubScript(slug=slug, tags=[])
        db.add(row)
    row.name = manifest.name
    row.description = manifest.description
    row.version = manifest.version
    row.author = manifest.author
    row.homepage = manifest.homepage
    row.icon_svg = _extract_icon(target, manifest)
    row.manifest_yaml = manifest_text
    row.fields_summary = summarize_fields(manifest)
    row.file_count = bundle_svc.count_bundle_files(target)
    row.bundle_sha256 = sha
    row.size_bytes = size
    db.flush()
    return row, created


def _ingest(db: Session, script_dir: Path, *, force: bool, move: bool = False) -> HubScript:
    """把一个含 manifest.yaml 的脚本目录落盘到 scripts_root 并入库。"""
    info = bundle_svc.validate_script_dir(script_dir)
    manifest = info["manifest"]
    manifest_text: str = info["manifest_text"]
    slug = manifest.slug
    bundle_svc.validate_slug(slug)

    root = _scripts_root()
    target = root / slug
    existing = db.execute(select(HubScript).where(HubScript.slug == slug)).scalar_one_or_none()
    if (target.exists() or existing) and not force:
        raise ConflictError(
            f"脚本 {slug!r} 已存在；如需覆盖请用 force=true",
            details={"slug": slug},
        )

    if target.exists():
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    src = Path(script_dir)
    if move:
        shutil.move(str(src), str(target))
    else:
        shutil.copytree(src, target)

    row, created = _upsert_row(db, slug, manifest, manifest_text, target)
    logger.info("货架入库 slug={} created={} files={} size={}", slug, created, row.file_count, row.size_bytes)
    return row, created


def import_from_zip(db: Session, data: bytes, *, force: bool = False) -> tuple[HubScript, bool]:
    """从上传的 zip 字节入库（解压到临时目录 → 校验 → 落盘 → upsert）。"""
    tmp_parent = Path(tempfile.mkdtemp(prefix="hub_upload_"))
    try:
        zip_path = tmp_parent / "upload.zip"
        zip_path.write_bytes(data)
        extract_dir = tmp_parent / "extracted"
        extract_dir.mkdir()
        bundle_svc.extract_zip_to_tmp(zip_path, extract_dir)
        return _ingest(db, extract_dir, force=force, move=True)
    finally:
        shutil.rmtree(tmp_parent, ignore_errors=True)


def import_from_dir(db: Session, src_dir: Path, *, force: bool = False) -> tuple[HubScript, bool]:
    """从一个已存在的脚本目录入库（种子导入用，copytree 不破坏源）。"""
    return _ingest(db, Path(src_dir), force=force, move=False)


def refresh_metadata(db: Session, slug: str) -> HubScript:
    """重新从磁盘解析 manifest + 重算 bundle，更新元数据（在线编辑后调用）。"""
    root = _scripts_root()
    target = root / slug
    if not target.is_dir():
        raise ScriptNotFound(f"脚本不存在: {slug}", details={"slug": slug})
    manifest_path = target / "manifest.yaml"
    manifest = parse_manifest(manifest_path)
    bundle_svc.validate_slug(manifest.slug)
    if manifest.slug != slug:
        raise ValidationError(
            "manifest.slug 与目录名不一致，不允许通过编辑改 slug",
            details={"dir": slug, "manifest_slug": manifest.slug},
        )
    manifest_text = manifest_path.read_text(encoding="utf-8")
    row, _ = _upsert_row(db, slug, manifest, manifest_text, target)
    return row


# ============================================================
# 删除 / 打包下载
# ============================================================
def delete_script(db: Session, slug: str) -> None:
    row = get_script(db, slug)
    db.delete(row)
    target = _scripts_root() / slug
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    db.flush()
    logger.info("货架删除 slug={}", slug)


def bundle_zip(db: Session, slug: str) -> bytes:
    """打包脚本为标准 zip 并自增下载计数，返回 zip 字节。"""
    row = get_script(db, slug)
    data, _sha, _size = bundle_svc.compute_script_bundle(_scripts_root(), slug)
    row.download_count = (row.download_count or 0) + 1
    db.flush()
    return data


# ============================================================
# 在线编辑（路径安全）
# ============================================================
def _safe_path(slug: str, relpath: str) -> Path:
    root = _scripts_root()
    target = (root / slug).resolve()
    if not target.is_dir():
        raise ScriptNotFound(f"脚本不存在: {slug}", details={"slug": slug})
    p = (target / relpath).resolve()
    try:
        p.relative_to(target)
    except ValueError as exc:
        raise PermissionError(
            "路径逃出脚本目录", details={"slug": slug, "path": relpath}
        ) from exc
    return p


def list_files(slug: str) -> list[dict]:
    root = _scripts_root()
    target = root / slug
    if not target.is_dir():
        raise ScriptNotFound(f"脚本不存在: {slug}", details={"slug": slug})
    items: list[dict] = []
    for p in sorted(target.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(target)
        if any(part in bundle_svc.BUNDLE_EXCLUDE_DIRS for part in rel.parts):
            continue
        size = p.stat().st_size
        editable = p.suffix.lower() not in bundle_svc.BINARY_SUFFIXES and size <= bundle_svc.MAX_FILE_BYTES
        items.append({"path": rel.as_posix(), "size": size, "editable": editable})
    return items


def read_file(slug: str, relpath: str) -> str:
    p = _safe_path(slug, relpath)
    if not p.is_file():
        raise ScriptNotFound("文件不存在", details={"slug": slug, "path": relpath})
    if p.suffix.lower() in bundle_svc.BINARY_SUFFIXES:
        raise ValidationError("二进制文件不可读取为文本", details={"path": relpath})
    if p.stat().st_size > bundle_svc.MAX_FILE_BYTES:
        raise PayloadTooLarge("文件过大", details={"path": relpath, "limit": bundle_svc.MAX_FILE_BYTES})
    return p.read_text(encoding="utf-8")


def write_file(db: Session, slug: str, relpath: str, content: str) -> HubScript:
    """写单文件 + 刷新元数据。编辑 manifest.yaml 会先预校验（非法则不落盘）。"""
    p = _safe_path(slug, relpath)
    if p.suffix.lower() in bundle_svc.BINARY_SUFFIXES:
        raise ValidationError("二进制文件不可在线编辑", details={"path": relpath})
    encoded = content.encode("utf-8")
    if len(encoded) > bundle_svc.MAX_FILE_BYTES:
        raise PayloadTooLarge("内容过大", details={"path": relpath, "limit": bundle_svc.MAX_FILE_BYTES})
    # 改 manifest.yaml 先预校验，非法则不落盘（避免损坏元数据）
    if Path(relpath).name == "manifest.yaml":
        parse_manifest_text(content, source=relpath)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return refresh_metadata(db, slug)
