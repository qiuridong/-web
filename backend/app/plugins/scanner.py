"""扫描 ``scripts/`` 目录差异 + 同步到 ``scripts`` 表。

详见 `进度/设计/后端架构.md` § 2.2 (POST /scripts/scan)。

流程:
1. 列举 ``scripts_dir`` 下每个**直接子目录**
2. 若该子目录下存在 ``manifest.yaml`` → 解析 + 计算 hash + 调 service.upsert_script
3. 若解析失败 → 记入 errors,继续下一个目录(部分失败不影响整体)
4. DB 中存在但磁盘已不存在的 slug → 标记为 removed,设 ``enabled=False``,
   **不级联删除** instance / run(留待用户手动 DELETE)
5. 返回 ``ScanResult`` dict(便于直接 jsonable)

注意:本模块不直接操作 DB,所有写入走 ``script_service`` 函数,确保 service 层
拥有完整的事务/缓存控制权。
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, TypedDict

from loguru import logger

from app.core.exceptions import ManifestInvalidError
from app.plugins.manifest import compute_hash, parse_manifest

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class ScanError(TypedDict):
    """扫描中单个目录的失败信息。"""

    slug: str
    error: str


class ScanResult(TypedDict):
    """``scan_scripts_dir`` 返回结构 — 与 § 2.2 响应字段一致。"""

    added: list[str]
    updated: list[str]
    removed: list[str]
    errors: list[ScanError]


_MANIFEST_FILENAME = "manifest.yaml"


def scan_scripts_dir(scripts_dir: Path, db: Session) -> ScanResult:
    """全量扫描 ``scripts_dir`` 子目录,差异同步到 DB。

    与 ``script_service`` 通过 ``upsert_script`` / ``mark_removed`` 协作,
    本模块只负责"发现 + diff",不直接 commit。调用方(service.scan_all)
    负责事务边界。

    :param scripts_dir: 脚本根目录(通常 ``settings.scripts_dir``)
    :param db: SQLAlchemy session
    :returns: :class:`ScanResult`
    """
    # 延迟 import 防循环(scanner ↔ script_service)
    from app.services import script_service

    result: ScanResult = {
        "added": [],
        "updated": [],
        "removed": [],
        "errors": [],
    }

    scripts_dir = Path(scripts_dir).resolve()
    if not scripts_dir.is_dir():
        logger.warning("scripts_dir 不存在或不是目录,跳过扫描 path={}", scripts_dir)
        return result

    found_slugs: set[str] = set()

    for child in sorted(scripts_dir.iterdir()):
        if not child.is_dir():
            continue
        # 跳过隐藏 / 下划线开头(_local_data 等本地状态目录)
        if child.name.startswith(".") or child.name.startswith("_"):
            continue

        manifest_path = child / _MANIFEST_FILENAME
        if not manifest_path.is_file():
            # 无 manifest.yaml → 不当作脚本目录,静默跳过
            continue

        # —— 解析 + 入库 ——
        slug_hint = child.name  # 仅用于错误上报;实际 slug 由 manifest 决定
        try:
            text = manifest_path.read_text(encoding="utf-8")
            manifest = parse_manifest(manifest_path)
            manifest_hash = compute_hash(text)

            # slug 与目录名不一致 → 报错(§ 3.1 约定一致)
            if manifest.slug != child.name:
                raise ManifestInvalidError(
                    message=(
                        f"manifest.slug ({manifest.slug!r}) 与目录名 ({child.name!r}) 不一致"
                    ),
                    details={"slug": manifest.slug, "dir": child.name},
                )

            _script, was_new, was_changed = script_service.upsert_script(
                db,
                manifest=manifest,
                manifest_path=str(manifest_path.resolve()),
                manifest_hash=manifest_hash,
            )
            found_slugs.add(manifest.slug)
            if was_new:
                result["added"].append(manifest.slug)
            elif was_changed:
                result["updated"].append(manifest.slug)
            # 否则:hash 未变,skip(不进 added/updated)
        except ManifestInvalidError as exc:
            logger.warning(
                "manifest 校验失败 slug={} path={} error={}",
                slug_hint,
                manifest_path,
                exc.message,
            )
            result["errors"].append({"slug": slug_hint, "error": exc.message})
        except Exception as exc:  # 防御:OSError / 任意未预料异常
            logger.exception(
                "扫描 {} 时出现未预料的异常",
                manifest_path,
            )
            result["errors"].append(
                {"slug": slug_hint, "error": f"{type(exc).__name__}: {exc}"}
            )

    # —— 标记磁盘已不存在的脚本 ——
    removed_slugs = script_service.mark_removed(db, present_slugs=found_slugs)
    result["removed"].extend(removed_slugs)

    logger.info(
        "扫描完成 added={} updated={} removed={} errors={}",
        len(result["added"]),
        len(result["updated"]),
        len(result["removed"]),
        len(result["errors"]),
    )
    return result
