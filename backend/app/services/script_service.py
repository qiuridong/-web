"""脚本 service — 扫描 manifest、CRUD、列表分页。

实现见 `进度/设计/后端架构.md` § 2.2 + § 1.2 + § 3。

公开函数
--------
- ``list_scripts(db, *, enabled, q, page, page_size) -> tuple[list[Script], int]``
- ``get_script_by_slug(db, slug) -> Script``                单个;不存在抛 ScriptNotFound
- ``get_script_detail(db, slug) -> dict``                   详情(含 fields_schema / readme / icon_url / requirements_present)
- ``upsert_script(db, *, manifest, manifest_path, manifest_hash) -> tuple[Script, bool, bool]``
                                                            返回 (script, was_new, was_changed)
- ``mark_removed(db, *, present_slugs) -> list[str]``       磁盘已不存在的脚本 → 标记 enabled=False
- ``enable_script(db, slug) -> Script``
- ``disable_script(db, slug) -> Script``
- ``delete_script(db, slug) -> None``
- ``scan_all(db, scripts_dir) -> dict``                     调 scanner.scan_scripts_dir,返回 jsonable dict

设计要点
--------
- 全部用 SQLAlchemy 2 风格 (``select(...)`` + ``session.scalars()``)
- 错误统一抛 ``app.core.exceptions.*``,不抛 HTTPException
- service 层负责 ``db.flush()``;``db.commit()`` 留给路由层(便于事务边界控制)
- ``upsert_script`` 与 ``mark_removed`` 是 scanner 的协作伙伴,scanner 不直接写 DB
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import ScriptNotFound
from app.db.models.instance import Instance
from app.db.models.script import Script
from app.plugins.scanner import scan_scripts_dir

if TYPE_CHECKING:
    from app.plugins.manifest import Manifest


# ============================================================
# 列表 / 详情 / 单查
# ============================================================
def list_scripts(
    db: Session,
    *,
    enabled: bool | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Script], int]:
    """分页列表 + 可选过滤。

    :param enabled: ``True``/``False`` 过滤启用状态;``None`` 表示全部
    :param q: 模糊匹配 ``slug`` 或 ``name``(LIKE %q%,大小写不敏感)
    :param page: 1-based 页码
    :param page_size: 每页条数
    :returns: ``(items, total)``
    """
    stmt = select(Script)
    count_stmt = select(func.count()).select_from(Script)

    if enabled is not None:
        stmt = stmt.where(Script.enabled == enabled)
        count_stmt = count_stmt.where(Script.enabled == enabled)

    if q:
        like = f"%{q}%"
        cond = or_(Script.slug.ilike(like), Script.name.ilike(like))
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)

    total = int(db.execute(count_stmt).scalar_one())

    offset = max(0, (page - 1) * page_size)
    stmt = stmt.order_by(Script.slug.asc()).offset(offset).limit(page_size)
    items = list(db.scalars(stmt).all())

    return items, total


def list_scripts_with_counts(
    db: Session,
    *,
    enabled: bool | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[tuple[Script, int]], int]:
    """audit High #7:列表 + instance_count 一次 SQL 拉出(消除 N+1)。

    替代旧版"先 list_scripts,再对每条调 _count_instances_for"路径
    (后者在 page_size=20 时多发 20 次 COUNT SQL)。

    本函数用 ``outerjoin + group_by`` 一次查询拉出 ``(Script, instance_count)``
    元组列表;count 走 SQL ``COUNT(Instance.id)``,空时为 0。

    :returns: ``([(Script, instance_count), ...], total)``
    """
    # 同样的 where 子句,先单独算 total 避免 group by 影响 count
    where_clauses: list[Any] = []
    if enabled is not None:
        where_clauses.append(Script.enabled == enabled)
    if q:
        like = f"%{q}%"
        where_clauses.append(or_(Script.slug.ilike(like), Script.name.ilike(like)))

    count_stmt = select(func.count()).select_from(Script)
    if where_clauses:
        for c in where_clauses:
            count_stmt = count_stmt.where(c)
    total = int(db.execute(count_stmt).scalar_one())

    # outerjoin Instance + group by Script.id —— SQLite 支持 GROUP BY 单列
    # 后选 Script 全部列
    stmt = (
        select(Script, func.count(Instance.id).label("instance_count"))
        .outerjoin(Instance, Instance.script_id == Script.id)
        .group_by(Script.id)
    )
    if where_clauses:
        for c in where_clauses:
            stmt = stmt.where(c)

    offset = max(0, (page - 1) * page_size)
    stmt = stmt.order_by(Script.slug.asc()).offset(offset).limit(page_size)

    rows = db.execute(stmt).all()
    items = [(row[0], int(row[1] or 0)) for row in rows]
    return items, total


def get_script_by_slug(db: Session, slug: str) -> Script:
    """按 slug 取单个;不存在抛 :class:`ScriptNotFound`。"""
    script = db.scalars(select(Script).where(Script.slug == slug)).one_or_none()
    if script is None:
        raise ScriptNotFound(
            message=f"脚本不存在: {slug!r}",
            details={"slug": slug},
        )
    return script


def _count_instances_for(db: Session, script_id: int) -> int:
    """统计指定 script 的实例数(供详情/列表 instance_count 字段)。"""
    return int(
        db.execute(
            select(func.count())
            .select_from(Instance)
            .where(Instance.script_id == script_id)
        ).scalar_one()
    )


def get_script_detail(db: Session, slug: str) -> dict[str, Any]:
    """详情(在 Script 基础上加 fields_schema / requirements_present / readme_md / icon_url)。

    返回 dict(便于直接 ``ScriptDetail.model_validate(...)``)。

    - ``fields_schema``:从 ``fields_schema_json`` 反序列化的列表
    - ``requirements_present``:同目录是否存在 ``requirements.txt``
    - ``readme_md``:同目录 ``README.md`` 原文(若存在);否则 ``None``
    - ``icon_url``:暂不暴露静态目录,统一返回 ``None``(前端可显示默认图标)
    """
    script = get_script_by_slug(db, slug)

    # 解析 fields_schema_json
    try:
        fields_schema = json.loads(script.fields_schema_json or "[]")
    except json.JSONDecodeError as exc:
        logger.warning(
            "fields_schema_json 解析失败 slug={} err={}", slug, exc
        )
        fields_schema = []

    # 同目录附属文件
    manifest_path = Path(script.manifest_path)
    script_dir = manifest_path.parent

    requirements_present = (script_dir / "requirements.txt").is_file()

    readme_path = script_dir / "README.md"
    readme_md: str | None = None
    if readme_path.is_file():
        try:
            readme_md = readme_path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("README.md 读取失败 path={} err={}", readme_path, exc)

    # icon_url:v1 不暴露静态目录(后端没挂 /static),先返回 None
    # 后续若挂上 StaticFiles,这里改成 f"/static/scripts/{slug}/{icon_rel}"
    icon_url: str | None = None

    instance_count = _count_instances_for(db, script.id)

    # 把 ORM 字段拉出来(避免 ScriptDetail.model_validate 时再访问 lazy 属性)
    return {
        "id": script.id,
        "slug": script.slug,
        "name": script.name,
        "description": script.description,
        "version": script.version,
        "author": script.author,
        "homepage": script.homepage,
        "default_cron": script.default_cron,
        "default_timeout_sec": script.default_timeout_sec,
        "enabled": script.enabled,
        "requires_secret": script.requires_secret,
        "instance_count": instance_count,
        "manifest_path": script.manifest_path,
        "manifest_hash": script.manifest_hash,
        "last_scanned_at": script.last_scanned_at,
        "created_at": script.created_at,
        "updated_at": script.updated_at,
        "fields_schema": fields_schema,
        "requirements_present": requirements_present,
        "readme_md": readme_md,
        "icon_url": icon_url,
    }


# ============================================================
# Scan / Upsert / Mark removed
# ============================================================
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _serialize_fields(manifest: Manifest) -> str:
    """把 manifest.fields 序列化为 JSON 字符串(用于 ``fields_schema_json``)。

    优先 ``model_dump(mode="json", by_alias=True)`` —— 让 ``schema_`` 输出为 ``schema``。
    """
    items = [
        f.model_dump(mode="json", by_alias=True, exclude_none=True)
        for f in manifest.fields
    ]
    return json.dumps(items, ensure_ascii=False)


def upsert_script(
    db: Session,
    *,
    manifest: Manifest,
    manifest_path: str,
    manifest_hash: str,
) -> tuple[Script, bool, bool]:
    """按 slug upsert。

    返回三元组 ``(script, was_new, was_changed)``:

    - 不存在 → INSERT,返回 ``(new, True, True)``
    - 存在 + hash 相同 → 仅更新 ``last_scanned_at``,返回 ``(existing, False, False)``
    - 存在 + hash 不同 → UPDATE 全部字段,返回 ``(updated, False, True)``

    scanner 据此判断 ``added`` / ``updated``。
    """
    now = _utcnow()
    existing = db.scalars(
        select(Script).where(Script.slug == manifest.slug)
    ).one_or_none()

    if existing is None:
        # —— INSERT ——
        new = Script(
            slug=manifest.slug,
            name=manifest.name,
            description=manifest.description,
            version=manifest.version,
            author=manifest.author,
            homepage=manifest.homepage,
            default_cron=manifest.default_cron,
            default_timeout_sec=manifest.default_timeout_sec,
            fields_schema_json=_serialize_fields(manifest),
            requires_secret=manifest.requires_secret,
            enabled=True,
            manifest_path=manifest_path,
            manifest_hash=manifest_hash,
            last_scanned_at=now,
        )
        db.add(new)
        db.flush()
        logger.info("新增脚本 slug={} version={}", new.slug, new.version)
        return new, True, True

    # —— 已存在 ——
    if existing.manifest_hash == manifest_hash:
        # 内容未变,只更新 last_scanned_at(轻量)
        existing.last_scanned_at = now
        db.flush()
        return existing, False, False

    # —— hash 不同 → UPDATE 全字段 ——
    existing.name = manifest.name
    existing.description = manifest.description
    existing.version = manifest.version
    existing.author = manifest.author
    existing.homepage = manifest.homepage
    existing.default_cron = manifest.default_cron
    existing.default_timeout_sec = manifest.default_timeout_sec
    existing.fields_schema_json = _serialize_fields(manifest)
    existing.requires_secret = manifest.requires_secret
    existing.manifest_path = manifest_path
    existing.manifest_hash = manifest_hash
    existing.last_scanned_at = now
    db.flush()
    logger.info("更新脚本 slug={} version={}", existing.slug, existing.version)
    return existing, False, True


def mark_removed(db: Session, *, present_slugs: set[str]) -> list[str]:
    """磁盘已不存在的 slug → ``enabled=False`` 并返回这些 slug。

    设计稿 § 2.2 约定:扫描发现 DB 中存在但磁盘不存在的脚本 → ``removed`` 数组,
    **不级联删除** instance / run(留待用户手动 DELETE)。这里只把 enabled 翻成 False。
    """
    all_slugs = list(db.scalars(select(Script.slug)).all())
    removed: list[str] = []
    for slug in all_slugs:
        if slug in present_slugs:
            continue
        existing = db.scalars(select(Script).where(Script.slug == slug)).one_or_none()
        if existing is None:
            continue
        if existing.enabled:
            existing.enabled = False
            db.flush()
            logger.info("磁盘缺失,禁用脚本 slug={}", slug)
        removed.append(slug)
    return removed


def scan_all(db: Session, scripts_dir: Path) -> dict[str, Any]:
    """触发全量扫描;返回 jsonable dict(便于直接 ``ScanResultResponse.model_validate``)。

    注意:本函数自身**不 commit**;路由层应在调用后 ``db.commit()``。
    """
    scripts_dir = Path(scripts_dir)
    logger.info("scan 开始 dir={}", scripts_dir)
    result = scan_scripts_dir(scripts_dir, db)
    # ScanResult 已经是 TypedDict(纯 dict),直接返回
    return dict(result)


# ============================================================
# Enable / Disable / Delete
# ============================================================
def enable_script(
    db: Session,
    slug: str,
    scheduler: Any | None = None,
) -> Script:
    """启用 script(``enabled=True``)。

    注意:启用 script 不自动启用其下被禁用的 instance(``instance.enabled``)。
    但对已启用(``instance.enabled=True``)的子实例,需要把它们重新注册回 scheduler,
    因为禁用 script 时是从 scheduler 摘的(audit High #11 修复)。
    """
    script = get_script_by_slug(db, slug)
    if not script.enabled:
        script.enabled = True
        db.flush()
        logger.info("启用脚本 slug={}", slug)

    # 把 script 旗下所有 enabled instance 重新注册到 scheduler
    if scheduler is not None and hasattr(scheduler, "register"):
        for inst in db.scalars(
            select(Instance).where(
                Instance.script_id == script.id,
                Instance.enabled.is_(True),
            )
        ).all():
            try:
                scheduler.register(inst)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "enable_script: scheduler.register 失败 instance={} err={}",
                    inst.id,
                    exc,
                )
    return script


def disable_script(
    db: Session,
    slug: str,
    scheduler: Any | None = None,
) -> Script:
    """禁用 script(``enabled=False``)。

    设计稿 § 2.2:禁用 script 会**暂停其所有实例的调度但不删**。
    audit High #11:之前只翻 ``scripts.enabled``,scheduler 任由 cron 触发后才在
    executor 自检跳过 — 产生无效日志/占 scheduler 槽位。现在同时调
    ``scheduler.unregister`` 把所有 instance job 摘掉。
    """
    script = get_script_by_slug(db, slug)
    if script.enabled:
        script.enabled = False
        db.flush()
        logger.info("禁用脚本 slug={}", slug)

    # 真停 scheduler:遍历该 script 下所有 instance,unregister
    if scheduler is not None and hasattr(scheduler, "unregister"):
        for inst in db.scalars(
            select(Instance).where(Instance.script_id == script.id)
        ).all():
            try:
                scheduler.unregister(inst.id)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "disable_script: scheduler.unregister 失败 instance={} err={}",
                    inst.id,
                    exc,
                )
    return script


def delete_script(db: Session, slug: str) -> None:
    """从 DB 删除脚本登记(级联删 instance / run);**不删磁盘文件**。

    由于 ``Script.instances`` 关系定义了 ``cascade="all, delete-orphan"``
    且 FK 是 ``ON DELETE CASCADE``,直接 ``db.delete()`` 即可级联。
    """
    script = get_script_by_slug(db, slug)
    db.delete(script)
    db.flush()
    logger.info("删除脚本登记 slug={}(磁盘文件保留)", slug)
