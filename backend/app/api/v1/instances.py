"""脚本实例 API — `/api/v1/instances/*`。

实现见 `进度/设计/后端架构.md` § 2.3 + § 5.2。

端点清单(11 个)
----------------
- GET    /instances                  🔒
- POST   /instances                  🔒 严格按 fields_schema 校验,secret 加密落库
- GET    /instances/{id}             🔒 secret 自动脱敏
- PATCH  /instances/{id}             🔒 secret 未提交 = 保留原值
- DELETE /instances/{id}             🔒 级联删 runs
- POST   /instances/{id}/enable      🔒
- POST   /instances/{id}/disable     🔒
- POST   /instances/{id}/pause       🔒 { until: ISO8601 }
- POST   /instances/{id}/resume      🔒
- POST   /instances/{id}/run         🔒 立即触发,返回 { run_id }
- POST   /instances/{id}/test        🔒 试运行,不写 runs/不发通知
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request, Response, status
from loguru import logger

from app.core.crypto import get_cipher
from app.db.models.user import User
from app.deps import CurrentUser, DBSession, Pagination, get_scheduler
from app.schemas.instance import (
    InstanceCreate,
    InstanceDetail,
    InstanceListItem,
    InstanceListResponse,
    InstancePauseRequest,
    InstanceRunResponse,
    InstanceTestResponse,
    InstanceUpdate,
)
from app.services import instance_service

router = APIRouter(prefix="/instances", tags=["instances"])


# ============================================================
# 列表
# ============================================================
@router.get(
    "",
    response_model=InstanceListResponse,
    summary="实例列表(分页 + 可选筛选)",
)
def list_instances(
    db: DBSession,
    _user: CurrentUser,
    pagination: Pagination,
    script_slug: Annotated[
        str | None,
        Query(description="按 script slug 筛选", max_length=64),
    ] = None,
    enabled: Annotated[
        bool | None,
        Query(description="按启用状态筛选"),
    ] = None,
    status_filter: Annotated[
        str | None,
        Query(
            alias="status",
            description="按 last_run_status 筛选",
            max_length=16,
        ),
    ] = None,
) -> InstanceListResponse:
    """🔒 返回 ``{ items, total, page, page_size }``。"""
    page, page_size = pagination
    items, total = instance_service.list_instances(
        db,
        script_slug=script_slug,
        enabled=enabled,
        status=status_filter,
        page=page,
        page_size=page_size,
    )
    return InstanceListResponse(
        items=[InstanceListItem.model_validate(it) for it in items],
        total=total,
        page=page,
        page_size=page_size,
    )


# ============================================================
# 创建
# ============================================================
@router.post(
    "",
    response_model=InstanceDetail,
    status_code=status.HTTP_201_CREATED,
    summary="创建实例(config 严格校验 + secret 加密落库)",
)
def create_instance(
    payload: InstanceCreate,
    request: Request,
    db: DBSession,
    _user: CurrentUser,
) -> InstanceDetail:
    """🔒 严格按 fields_schema 校验 config;secret 字段加密落库。"""
    scheduler = getattr(request.app.state, "scheduler", None)
    cipher = get_cipher()
    detail = instance_service.create_instance(
        db,
        payload=payload,
        cipher=cipher,
        scheduler=scheduler,
    )
    db.commit()
    # audit High #4:commit 后回写 next_run_at(service 内部 register 因外层未
    # commit 写不了 — 此处补一次保证落库)
    if scheduler is not None and detail.get("id"):
        try:
            next_run = scheduler.sync_next_run_at(detail["id"])
            # 把最新的 next_run_at 同步进响应 dict
            detail["next_run_at"] = next_run
        except Exception:  # noqa: BLE001
            pass
    return InstanceDetail.model_validate(detail)


# ============================================================
# 详情
# ============================================================
@router.get(
    "/{instance_id}",
    response_model=InstanceDetail,
    summary="实例详情(secret 自动脱敏)",
)
def get_instance(
    instance_id: int,
    db: DBSession,
    _user: CurrentUser,
) -> InstanceDetail:
    """🔒 secret 字段自动脱敏为 null,同时返回 `_secret_set` 指示已配置状态。"""
    detail = instance_service.get_instance_detail(
        db, instance_id, cipher=get_cipher()
    )
    return InstanceDetail.model_validate(detail)


# ============================================================
# 更新
# ============================================================
@router.patch(
    "/{instance_id}",
    response_model=InstanceDetail,
    summary="部分更新实例(secret 字段未提交 = 保留原值)",
)
def update_instance(
    instance_id: int,
    payload: InstanceUpdate,
    request: Request,
    db: DBSession,
    _user: CurrentUser,
) -> InstanceDetail:
    """🔒 关键语义:
    - secret 字段未提交 / None / 空字符串 → 保留原值
    - cron / enabled 变化时自动 reschedule
    """
    scheduler = getattr(request.app.state, "scheduler", None)
    detail = instance_service.update_instance(
        db,
        instance_id,
        payload,
        cipher=get_cipher(),
        scheduler=scheduler,
    )
    db.commit()
    # audit High #4:commit 后回写 next_run_at
    if scheduler is not None:
        try:
            detail["next_run_at"] = scheduler.sync_next_run_at(instance_id)
        except Exception:  # noqa: BLE001
            pass
    return InstanceDetail.model_validate(detail)


# ============================================================
# 删除
# ============================================================
@router.delete(
    "/{instance_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除实例(级联删 runs)",
)
def delete_instance(
    instance_id: int,
    request: Request,
    response: Response,
    db: DBSession,
    _user: CurrentUser,
) -> Response:
    """🔒 删除实例 + 级联删除其 runs + 从调度器摘除。"""
    scheduler = getattr(request.app.state, "scheduler", None)
    instance_service.delete_instance(db, instance_id, scheduler=scheduler)
    db.commit()
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


# ============================================================
# 启用 / 禁用
# ============================================================
@router.post(
    "/{instance_id}/enable",
    response_model=InstanceDetail,
    summary="启用实例(并注册到调度器)",
)
def enable_instance(
    instance_id: int,
    request: Request,
    db: DBSession,
    _user: CurrentUser,
) -> InstanceDetail:
    """🔒"""
    scheduler = getattr(request.app.state, "scheduler", None)
    detail = instance_service.enable_instance(
        db, instance_id, scheduler=scheduler, cipher=get_cipher()
    )
    db.commit()
    # audit High #4:commit 后回写 next_run_at
    if scheduler is not None:
        try:
            detail["next_run_at"] = scheduler.sync_next_run_at(instance_id)
        except Exception:  # noqa: BLE001
            pass
    return InstanceDetail.model_validate(detail)


@router.post(
    "/{instance_id}/disable",
    response_model=InstanceDetail,
    summary="禁用实例(从调度器摘除)",
)
def disable_instance(
    instance_id: int,
    request: Request,
    db: DBSession,
    _user: CurrentUser,
) -> InstanceDetail:
    """🔒"""
    scheduler = getattr(request.app.state, "scheduler", None)
    detail = instance_service.disable_instance(
        db, instance_id, scheduler=scheduler, cipher=get_cipher()
    )
    db.commit()
    # audit High #4:disable 后 next_run_at 应为 None(unregister 已清),
    # 但 detail 是 disable_instance 调用前序列化的,需要同步到响应
    if scheduler is not None:
        try:
            detail["next_run_at"] = scheduler.sync_next_run_at(instance_id)
        except Exception:  # noqa: BLE001
            pass
    return InstanceDetail.model_validate(detail)


# ============================================================
# 暂停 / 恢复
# ============================================================
@router.post(
    "/{instance_id}/pause",
    response_model=InstanceDetail,
    summary="临时暂停到指定时刻",
)
def pause_instance(
    instance_id: int,
    payload: InstancePauseRequest,
    request: Request,
    db: DBSession,
    _user: CurrentUser,
) -> InstanceDetail:
    """🔒 {until: ISO8601},到期由 scheduler 自动 resume。"""
    scheduler = getattr(request.app.state, "scheduler", None)
    detail = instance_service.pause_instance(
        db,
        instance_id,
        payload.until,
        scheduler=scheduler,
        cipher=get_cipher(),
    )
    db.commit()
    return InstanceDetail.model_validate(detail)


@router.post(
    "/{instance_id}/resume",
    response_model=InstanceDetail,
    summary="立即恢复(清除 paused_until)",
)
def resume_instance(
    instance_id: int,
    request: Request,
    db: DBSession,
    _user: CurrentUser,
) -> InstanceDetail:
    """🔒"""
    scheduler = getattr(request.app.state, "scheduler", None)
    detail = instance_service.resume_instance(
        db,
        instance_id,
        scheduler=scheduler,
        cipher=get_cipher(),
    )
    db.commit()
    return InstanceDetail.model_validate(detail)


# ============================================================
# 立即触发
# ============================================================
@router.post(
    "/{instance_id}/run",
    response_model=InstanceRunResponse,
    summary="立即触发一次执行",
)
def run_instance(
    instance_id: int,
    request: Request,
    db: DBSession,
    user: CurrentUser,
) -> InstanceRunResponse:
    """🔒 立即触发;返回 ``{ run_id }``;若并发槽位满会排队。"""
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is None:
        raise RuntimeError("Scheduler 尚未初始化")

    user_id = getattr(user, "id", None)
    run_id = instance_service.trigger_instance(
        db,
        instance_id,
        scheduler=scheduler,
        trigger_user_id=user_id,
        trigger_type="manual",
    )
    logger.info("用户 {} 手动触发 instance.{} → run.{}", user_id, instance_id, run_id)
    return InstanceRunResponse(run_id=run_id)


# ============================================================
# 试运行
# ============================================================
@router.post(
    "/{instance_id}/test",
    response_model=InstanceTestResponse,
    summary="试运行(不写 runs / 不发通知)",
)
async def test_instance(
    instance_id: int,
    db: DBSession,
    _user: CurrentUser,
) -> InstanceTestResponse:
    """🔒 完整跑一次 + 返回 stdout/stderr/result;不落 runs;不发通知。

    若该 instance 当前有 pending/running 的真实 run,返回 409。
    """
    result = await instance_service.test_instance(
        db, instance_id, cipher=get_cipher()
    )
    return InstanceTestResponse.model_validate(result)
