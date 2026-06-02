"""脚本打包 + zip 安全 + slug 校验（移植自主项目 ``script_upload_service.py``）。

**与管家保持完全相同的口径**，确保货架产出的 zip 一定能被签到管家接受：
- slug 正则 ``^[a-z][a-z0-9-]{0,40}$`` + 保留字
- zip 安全：拒 zip slip / 绝对路径 / 软链 / 单文件 256KiB / 总 1MiB / 文件数 200
- bundle 打包：过滤 .backups/__pycache__/data 等垃圾，sha256 摘要

去掉了管家的 dry-run（货架不运行脚本）。
"""
from __future__ import annotations

import hashlib
import io
import re
import shutil
from pathlib import Path
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile, ZipInfo

from loguru import logger

from app.core.exceptions import (
    PayloadTooLarge,
    PermissionError,
    ScriptNotFound,
    ValidationError,
)
from app.services.manifest import parse_manifest_text

# ============================================================
# 常量（与管家一致）
# ============================================================
MAX_ZIP_TOTAL_BYTES: int = 1 * 1024 * 1024
MAX_FILE_BYTES: int = 256 * 1024
BACKUPS_SUBDIR: str = ".backups"

RESERVED_SLUGS: frozenset[str] = frozenset({
    ".", "..", "new", "upload", "create", "edit", "delete",
    "scan", "test", "admin", "backups",
})

#: 打 bundle 时跳过的子目录
BUNDLE_EXCLUDE_DIRS: frozenset[str] = frozenset({
    BACKUPS_SUBDIR, "__pycache__", "data", ".git",
    "_dry_run_data", "node_modules", ".pytest_cache",
})

#: 打 bundle 时跳过的文件后缀
BUNDLE_EXCLUDE_SUFFIXES: frozenset[str] = frozenset({
    ".pyc", ".pyo", ".pyd", ".log", ".tmp", ".DS_Store",
})

#: 不可在线编辑的二进制后缀
BINARY_SUFFIXES: frozenset[str] = frozenset({
    ".pyc", ".pyo", ".pyd", ".so", ".dll", ".dylib", ".exe", ".bin",
    ".zip", ".gz", ".tar", ".bz2", ".xz", ".7z",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp",
    ".ico", ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".pdf", ".mp3", ".mp4", ".webm", ".ogg",
    ".db", ".sqlite", ".sqlite3",
})


# ============================================================
# slug 校验（管家口径：字母开头，长 1-41）
# ============================================================
def validate_slug(slug: str) -> None:
    """校验 slug 合规 + 不在保留字列表，口径与管家 ``validate_slug`` 完全一致。"""
    if not slug or not isinstance(slug, str):
        raise ValidationError("slug 不能为空", details={"field": "slug", "value": slug})
    if slug.lower() in RESERVED_SLUGS:
        raise PermissionError(
            f"slug {slug!r} 是保留字，不允许使用",
            details={"slug": slug, "reserved": sorted(RESERVED_SLUGS)},
        )
    if not re.compile(r"^[a-z][a-z0-9-]{0,40}$").match(slug):
        raise ValidationError(
            f"slug {slug!r} 不合法；必须匹配 ^[a-z][a-z0-9-]{{0,40}}$ "
            "(以小写字母开头，允许 a-z 0-9 -，总长 1-41)",
            details={"field": "slug", "value": slug},
        )


# ============================================================
# Zip 安全校验
# ============================================================
def validate_zip_safety(zip_path: Path) -> list[ZipInfo]:
    """遍历 zip 拒绝 zip slip / 超大文件 / 软链，返回安全 ZipInfo 列表。"""
    try:
        with ZipFile(zip_path, "r") as zf:
            infos = zf.infolist()
    except BadZipFile as exc:
        raise ValidationError(f"zip 文件解析失败: {exc}", details={"path": str(zip_path)}) from exc

    if len(infos) > 200:
        raise PayloadTooLarge(
            f"zip 包含 {len(infos)} 个条目，超过 200 上限",
            details={"count": len(infos), "limit": 200},
        )

    total = 0
    safe: list[ZipInfo] = []
    for info in infos:
        name = info.filename
        if name.endswith("/"):
            continue
        normalized = name.replace("\\", "/")
        if normalized.startswith("/") or ":" in normalized.split("/")[0]:
            raise PermissionError(f"zip 含绝对路径条目: {name!r}", details={"entry": name})
        if any(p == ".." for p in normalized.split("/")):
            raise PermissionError(f"zip 含 .. 路径段: {name!r}", details={"entry": name})
        mode = (info.external_attr >> 16) & 0xFFFF
        if mode and (mode & 0o170000) == 0o120000:
            raise PermissionError(f"zip 含软链条目: {name!r}", details={"entry": name})
        if info.file_size > MAX_FILE_BYTES:
            raise PayloadTooLarge(
                f"zip 单文件 {name!r} 大小 {info.file_size} > 上限 {MAX_FILE_BYTES}",
                details={"entry": name, "size": info.file_size, "limit": MAX_FILE_BYTES},
            )
        total += info.file_size
        if total > MAX_ZIP_TOTAL_BYTES:
            raise PayloadTooLarge(
                f"zip 解压后总大小 > 上限 {MAX_ZIP_TOTAL_BYTES}",
                details={"current": total, "limit": MAX_ZIP_TOTAL_BYTES},
            )
        safe.append(info)
    return safe


def _detect_single_top_dir(infos: list[ZipInfo]) -> str | None:
    """若所有条目都在同一顶层目录下，返回该目录名；否则 None。"""
    if not infos:
        return None
    first = infos[0].filename.replace("\\", "/").split("/", 1)[0]
    for info in infos:
        name = info.filename.replace("\\", "/")
        if name.split("/", 1)[0] != first or "/" not in name:
            return None
    return first


def extract_zip_to_tmp(zip_path: Path, target_tmp: Path) -> list[str]:
    """把 zip 安全解压到 ``target_tmp``（已存在且为空），自动剥离顶层单一目录。"""
    target_tmp = Path(target_tmp)
    if not target_tmp.is_dir():
        raise ValidationError(f"解压目标目录不存在: {target_tmp}", details={"target": str(target_tmp)})

    safe_infos = validate_zip_safety(zip_path)
    top_dir = _detect_single_top_dir(safe_infos)
    if top_dir:
        logger.info("zip 顶层单一目录 {!r}，解压时自动剥离", top_dir)

    written: list[str] = []
    with ZipFile(zip_path, "r") as zf:
        for info in safe_infos:
            rel = info.filename.replace("\\", "/")
            if top_dir and rel.startswith(top_dir + "/"):
                rel = rel[len(top_dir) + 1:]
            if not rel:
                continue
            dest = target_tmp / rel
            try:
                dest.resolve().relative_to(target_tmp.resolve())
            except ValueError as exc:
                raise PermissionError(
                    f"解压目标路径逃出 target_tmp: {dest}",
                    details={"entry": info.filename},
                ) from exc
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out, length=64 * 1024)
            written.append(rel)
    return written


# ============================================================
# 脚本目录结构校验
# ============================================================
def validate_script_dir(tmp_dir: Path) -> dict:
    """校验目录构成合法脚本（必含 manifest.yaml + schema 通过），返回解析结果。"""
    tmp_dir = Path(tmp_dir)
    manifest_path = tmp_dir / "manifest.yaml"
    if not manifest_path.is_file():
        raise ValidationError(
            "上传内容缺少 manifest.yaml（脚本目录根必须有此文件）",
            details={"tmp_dir": str(tmp_dir)},
        )
    text = manifest_path.read_text(encoding="utf-8")
    manifest = parse_manifest_text(text, source=manifest_path)
    return {
        "slug": manifest.slug,
        "name": manifest.name,
        "version": manifest.version,
        "manifest": manifest,
        "manifest_text": text,
        "has_main_py": (tmp_dir / "main.py").is_file(),
    }


# ============================================================
# Bundle 打包
# ============================================================
def compute_script_bundle(scripts_root: Path, slug: str) -> tuple[bytes, str, int]:
    """打包 ``scripts_root/<slug>/`` 为 zip，返回 ``(bytes, sha256_hex, size)``。

    过滤 :data:`BUNDLE_EXCLUDE_DIRS` / :data:`BUNDLE_EXCLUDE_SUFFIXES` / 点开头文件。
    """
    scripts_root = Path(scripts_root).resolve()
    target = scripts_root / slug
    if not target.is_dir():
        raise ScriptNotFound(f"脚本目录不存在: {slug}", details={"slug": slug, "path": str(target)})
    try:
        target.resolve().relative_to(scripts_root)
    except ValueError as exc:
        raise PermissionError(
            f"slug 路径逃出 scripts_root: {target}", details={"slug": slug}
        ) from exc

    buf = io.BytesIO()
    file_count = 0
    raw_total = 0
    with ZipFile(buf, "w", compression=ZIP_DEFLATED, compresslevel=6) as zf:
        for path in sorted(target.rglob("*")):
            if not path.is_file():
                continue
            try:
                rel = path.relative_to(target)
            except ValueError:
                continue
            if any(p in BUNDLE_EXCLUDE_DIRS for p in rel.parts):
                continue
            if path.suffix.lower() in BUNDLE_EXCLUDE_SUFFIXES:
                continue
            base = rel.name
            if base.startswith(".") and base not in {".gitignore", ".env.example"}:
                continue
            raw_total += path.stat().st_size
            if raw_total > MAX_ZIP_TOTAL_BYTES:
                raise PayloadTooLarge(
                    f"脚本 {slug!r} 原始大小 > 上限 {MAX_ZIP_TOTAL_BYTES} 字节",
                    details={"slug": slug, "raw_total": raw_total, "limit": MAX_ZIP_TOTAL_BYTES},
                )
            zf.write(path, arcname=rel.as_posix())
            file_count += 1

    if file_count == 0:
        raise ValidationError(f"脚本 {slug!r} 过滤后没有任何文件，打包失败", details={"slug": slug})

    data = buf.getvalue()
    if len(data) > MAX_ZIP_TOTAL_BYTES:
        raise PayloadTooLarge(
            f"脚本 {slug!r} 压缩后 {len(data)} > 上限 {MAX_ZIP_TOTAL_BYTES} 字节",
            details={"slug": slug, "size": len(data), "limit": MAX_ZIP_TOTAL_BYTES},
        )
    sha = hashlib.sha256(data).hexdigest()
    logger.debug("compute_script_bundle slug={} files={} zip={} sha={}", slug, file_count, len(data), sha[:12])
    return data, sha, len(data)


def count_bundle_files(target: Path) -> int:
    """统计 ``target`` 下过滤后的文件数（与 bundle 口径一致）。"""
    target = Path(target)
    n = 0
    for path in target.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(target)
        if any(p in BUNDLE_EXCLUDE_DIRS for p in rel.parts):
            continue
        if path.suffix.lower() in BUNDLE_EXCLUDE_SUFFIXES:
            continue
        if rel.name.startswith(".") and rel.name not in {".gitignore", ".env.example"}:
            continue
        n += 1
    return n
