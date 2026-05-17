"""脚本插件 API — `/api/v1/scripts/*`。

实现见 `进度/设计/后端架构.md` § 2.2。

端点清单(6 个):
- GET    /scripts                🔒 列表 + 分页 + 可选 enabled / q 过滤
- GET    /scripts/{slug}         🔒 详情(含 fields_schema / readme / icon_url / requirements_present)
- POST   /scripts/scan           🔒 触发全量扫描
- POST   /scripts/{slug}/enable  🔒 启用
- POST   /scripts/{slug}/disable 🔒 禁用(暂停其所有实例的调度)
- DELETE /scripts/{slug}         🔒 删除(?confirm=true 必填,不删磁盘)

业务异常统一抛 ``app.core.exceptions.*``,由 ``error_handler`` 中间件转 § 8.2 标准响应。
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request, Response, status
from loguru import logger

from app.config import get_settings
from app.core.exceptions import ValidationError
from app.deps import CurrentUser, DBSession, Pagination
from app.schemas.script import (
    ScanResultResponse,
    ScriptDetail,
    ScriptListItem,
    ScriptListResponse,
)
from app.services import script_service

router = APIRouter(prefix="/scripts", tags=["scripts"])


# ============================================================
# 列表
# ============================================================
@router.get(
    "",
    response_model=ScriptListResponse,
    summary="脚本列表(分页 + 可选筛选)",
)
def list_scripts(
    db: DBSession,
    _user: CurrentUser,
    pagination: Pagination,
    enabled: Annotated[
        bool | None,
        Query(description="按启用状态筛选;省略 = 全部"),
    ] = None,
    q: Annotated[
        str | None,
        Query(description="模糊匹配 slug / name", max_length=64),
    ] = None,
) -> ScriptListResponse:
    """🔒 返回 ``{ items, total, page, page_size }``。

    audit High #7:用 ``list_scripts_with_counts`` 一次 SQL outerjoin + group by
    拉出 ``(Script, instance_count)`` 对,消除原 N+1(每条 COUNT)。
    """
    page, page_size = pagination
    items, total = script_service.list_scripts_with_counts(
        db,
        enabled=enabled,
        q=q,
        page=page,
        page_size=page_size,
    )

    list_items: list[ScriptListItem] = [
        ScriptListItem(
            id=s.id,
            slug=s.slug,
            name=s.name,
            description=s.description,
            version=s.version,
            default_cron=s.default_cron,
            enabled=s.enabled,
            requires_secret=s.requires_secret,
            instance_count=instance_count,
            last_scanned_at=s.last_scanned_at,
        )
        for s, instance_count in items
    ]

    return ScriptListResponse(
        items=list_items,
        total=total,
        page=page,
        page_size=page_size,
    )


# ============================================================
# 触发扫描(注意:必须放在 /{slug} 之前,否则 /scan 会被路由到 slug)
# ============================================================
@router.post(
    "/scan",
    response_model=ScanResultResponse,
    status_code=status.HTTP_200_OK,
    summary="触发全量扫描 scripts/ 目录",
)
def scan_scripts(
    db: DBSession,
    _user: CurrentUser,
) -> ScanResultResponse:
    """🔒 全量扫描 ``settings.scripts_dir``,差异同步到 DB。

    返回 ``{ added: [], updated: [], removed: [], errors: [{slug, error}] }``。
    """
    settings = get_settings()
    scripts_dir = settings.scripts_dir.resolve()
    logger.info("收到 scan 请求 dir={}", scripts_dir)

    result = script_service.scan_all(db, scripts_dir)
    db.commit()

    return ScanResultResponse(**result)


# ============================================================
# 详情
# ============================================================
@router.get(
    "/{slug}",
    response_model=ScriptDetail,
    summary="脚本详情",
)
def get_script(
    slug: str,
    db: DBSession,
    _user: CurrentUser,
) -> ScriptDetail:
    """🔒 返回详情 + ``fields_schema`` / ``requirements_present`` /
    ``readme_md`` / ``icon_url``。
    """
    detail = script_service.get_script_detail(db, slug)
    return ScriptDetail.model_validate(detail)


# ============================================================
# 启用 / 禁用
# ============================================================
@router.post(
    "/{slug}/enable",
    response_model=ScriptDetail,
    status_code=status.HTTP_200_OK,
    summary="全局启用脚本",
)
def enable(
    slug: str,
    request: Request,
    db: DBSession,
    _user: CurrentUser,
) -> ScriptDetail:
    """🔒 启用,响应同详情。

    同步对该 script 下所有 ``enabled=True`` instance 调
    ``scheduler.register`` 让 cron job 恢复(audit High #11)。
    commit 后再回写各 instance 的 ``next_run_at``(audit High #4)。
    """
    scheduler = getattr(request.app.state, "scheduler", None)
    script_service.enable_script(db, slug, scheduler)
    db.commit()
    # audit High #4:遍历该 script 旗下 instance,回写 next_run_at
    if scheduler is not None:
        from app.db.models.instance import Instance  # noqa: PLC0415
        from app.db.models.script import Script  # noqa: PLC0415
        from sqlalchemy import select as _select  # noqa: PLC0415
        script_id = db.scalars(
            _select(Script.id).where(Script.slug == slug)
        ).one_or_none()
        if script_id is not None:
            for inst_id in db.scalars(
                _select(Instance.id).where(Instance.script_id == script_id)
            ).all():
                try:
                    scheduler.sync_next_run_at(inst_id)
                except Exception:  # noqa: BLE001
                    pass
    detail = script_service.get_script_detail(db, slug)
    return ScriptDetail.model_validate(detail)


@router.post(
    "/{slug}/disable",
    response_model=ScriptDetail,
    status_code=status.HTTP_200_OK,
    summary="全局禁用脚本(暂停所有实例调度)",
)
def disable(
    slug: str,
    request: Request,
    db: DBSession,
    _user: CurrentUser,
) -> ScriptDetail:
    """🔒 禁用,响应同详情。

    同步对该 script 下所有 instance 调 ``scheduler.unregister``
    避免无效 cron 触发(audit High #11)。
    """
    scheduler = getattr(request.app.state, "scheduler", None)
    script_service.disable_script(db, slug, scheduler)
    db.commit()
    # audit High #4:disable_script 内 unregister 已清 next_run_at,但 _write_*
    # 用独立 session,SQLite commit 可能 race,再补一次保险
    if scheduler is not None:
        from app.db.models.instance import Instance  # noqa: PLC0415
        from app.db.models.script import Script  # noqa: PLC0415
        from sqlalchemy import select as _select  # noqa: PLC0415
        script_id = db.scalars(
            _select(Script.id).where(Script.slug == slug)
        ).one_or_none()
        if script_id is not None:
            for inst_id in db.scalars(
                _select(Instance.id).where(Instance.script_id == script_id)
            ).all():
                try:
                    scheduler.sync_next_run_at(inst_id)
                except Exception:  # noqa: BLE001
                    pass
    detail = script_service.get_script_detail(db, slug)
    return ScriptDetail.model_validate(detail)


# ============================================================
# 删除
# ============================================================
@router.delete(
    "/{slug}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="从 DB 删除脚本登记(不删磁盘)",
)
def delete(
    slug: str,
    response: Response,
    db: DBSession,
    _user: CurrentUser,
    confirm: Annotated[
        bool,
        Query(description="必须为 true,否则拒绝"),
    ] = False,
) -> Response:
    """🔒 必须带 ``?confirm=true``;级联删除其 instance / run,**不删磁盘文件**。"""
    if not confirm:
        raise ValidationError(
            message="删除脚本需要带 ?confirm=true 参数",
            details={"field": "confirm", "expected": True},
        )

    script_service.delete_script(db, slug)
    db.commit()
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
