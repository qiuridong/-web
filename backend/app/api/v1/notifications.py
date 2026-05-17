"""通知 API — `/api/v1/notifications/*`。

实现见 `进度/设计/后端架构.md` § 2.5。

渠道端点(6 个)
----------------
- ``GET    /notifications/channels``               🔒 列表,apprise_url 脱敏
- ``POST   /notifications/channels``               🔒 创建
- ``GET    /notifications/channels/{id}``          🔒 详情(脱敏)
- ``PATCH  /notifications/channels/{id}``          🔒 apprise_url 未传 = 保留原值
- ``DELETE /notifications/channels/{id}``          🔒 级联删规则
- ``POST   /notifications/channels/{id}/test``     🔒 立即试发,返回 (ok, latency_ms, error)

规则端点(5 + 1 个)
--------------------
- ``GET    /notifications/rules``                  🔒 列表 + 可选筛选
- ``POST   /notifications/rules``                  🔒 创建
- ``GET    /notifications/rules/{id}``             🔒 详情
- ``PATCH  /notifications/rules/{id}``             🔒 更新
- ``DELETE /notifications/rules/{id}``             🔒 删除
- ``POST   /notifications/rules/{id}/preview``     🔒 用假数据渲染,不发送
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.core.crypto import get_cipher
from app.deps import CurrentUser, DBSession
from app.notifications import apprise_client as _apprise_mod
from app.schemas.notification import (
    ChannelCreateRequest,
    ChannelListItem,
    ChannelPatchRequest,
    ChannelTestRequest,
    ChannelTestResponse,
    RuleCreateRequest,
    RuleListItem,
    RulePatchRequest,
    RulePreviewResponse,
)
from app.services import notification_service

router = APIRouter(prefix="/notifications", tags=["notifications"])


# ============================================================
# 渠道
# ============================================================
@router.get(
    "/channels",
    response_model=list[ChannelListItem],
    summary="渠道列表(apprise_url 自动脱敏)",
)
def list_channels(
    db: DBSession,
    _user: CurrentUser,
) -> list[ChannelListItem]:
    """🔒 返回全部渠道,按 name 升序。"""
    chs = notification_service.list_channels(db)
    return [
        ChannelListItem.model_validate(notification_service.to_list_item_dict(c))
        for c in chs
    ]


@router.post(
    "/channels",
    response_model=ChannelListItem,
    status_code=status.HTTP_201_CREATED,
    summary="新建渠道",
)
def create_channel(
    payload: ChannelCreateRequest,
    db: DBSession,
    _user: CurrentUser,
) -> ChannelListItem:
    """🔒 创建渠道;apprise_url 加密落库。"""
    cipher = get_cipher()
    ch = notification_service.create_channel(
        db,
        name=payload.name,
        type=payload.type,
        apprise_url=payload.apprise_url,
        description=payload.description,
        enabled=payload.enabled,
        cipher=cipher,
    )
    db.commit()
    db.refresh(ch)
    return ChannelListItem.model_validate(
        notification_service.to_list_item_dict(ch)
    )


@router.get(
    "/channels/{channel_id}",
    response_model=ChannelListItem,
    summary="渠道详情(脱敏)",
)
def get_channel(
    channel_id: int,
    db: DBSession,
    _user: CurrentUser,
) -> ChannelListItem:
    """🔒 不返回 apprise_url 明文。"""
    ch = notification_service.get_channel(db, channel_id)
    return ChannelListItem.model_validate(
        notification_service.to_list_item_dict(ch)
    )


@router.patch(
    "/channels/{channel_id}",
    response_model=ChannelListItem,
    summary="更新渠道(apprise_url 未传则保留原值)",
)
def update_channel(
    channel_id: int,
    payload: ChannelPatchRequest,
    db: DBSession,
    _user: CurrentUser,
) -> ChannelListItem:
    """🔒 PATCH;未传字段保留原值。"""
    cipher = get_cipher()
    ch = notification_service.update_channel(
        db, channel_id, patch=payload, cipher=cipher
    )
    db.commit()
    db.refresh(ch)
    return ChannelListItem.model_validate(
        notification_service.to_list_item_dict(ch)
    )


@router.delete(
    "/channels/{channel_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除渠道(级联删规则)",
)
def delete_channel(
    channel_id: int,
    response: Response,
    db: DBSession,
    _user: CurrentUser,
) -> Response:
    """🔒 级联删除其所有规则。"""
    notification_service.delete_channel(db, channel_id)
    db.commit()
    # 清池缓存(同步)
    pool = _apprise_mod.get_pool()
    pool._cache.pop(channel_id, None)  # noqa: SLF001
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post(
    "/channels/{channel_id}/test",
    response_model=ChannelTestResponse,
    status_code=status.HTTP_200_OK,
    summary="立即发送测试消息",
)
async def test_channel(
    channel_id: int,
    payload: ChannelTestRequest,
    db: DBSession,
    _user: CurrentUser,
) -> ChannelTestResponse:
    """🔒 立即试发一条;返回 ``(ok, latency_ms, error)``。

    无论成功失败,``last_test_at`` / ``last_test_ok`` 都会更新。
    """
    cipher = get_cipher()
    pool = _apprise_mod.get_pool()
    ok, latency_ms, err = await notification_service.test_channel(
        db,
        channel_id,
        title=payload.title,
        body=payload.body,
        cipher=cipher,
        pool=pool,
    )
    db.commit()
    return ChannelTestResponse(ok=ok, latency_ms=latency_ms, error=err)


# ============================================================
# 规则
# ============================================================
@router.get(
    "/rules",
    response_model=list[RuleListItem],
    summary="规则列表(可选筛选)",
)
def list_rules(
    db: DBSession,
    _user: CurrentUser,
    scope: Annotated[
        str | None, Query(description="按 scope 筛选(global/script/instance)")
    ] = None,
    script_id: Annotated[int | None, Query(description="按 script_id 筛选")] = None,
    instance_id: Annotated[
        int | None, Query(description="按 instance_id 筛选")
    ] = None,
    channel_id: Annotated[
        int | None, Query(description="按 channel_id 筛选")
    ] = None,
) -> list[RuleListItem]:
    """🔒 全部 enabled / disabled 规则。"""
    rules = notification_service.list_rules(
        db,
        scope=scope,
        script_id=script_id,
        instance_id=instance_id,
        channel_id=channel_id,
    )
    return [RuleListItem.model_validate(r) for r in rules]


@router.post(
    "/rules",
    response_model=RuleListItem,
    status_code=status.HTTP_201_CREATED,
    summary="新建规则",
)
def create_rule(
    payload: RuleCreateRequest,
    db: DBSession,
    _user: CurrentUser,
) -> RuleListItem:
    """🔒 新建规则;scope 与 script_id/instance_id 一致性由 service 层校验。"""
    rule = notification_service.create_rule(db, payload=payload)
    db.commit()
    db.refresh(rule)
    return RuleListItem.model_validate(rule)


@router.get(
    "/rules/{rule_id}",
    response_model=RuleListItem,
    summary="规则详情",
)
def get_rule(
    rule_id: int,
    db: DBSession,
    _user: CurrentUser,
) -> RuleListItem:
    """🔒"""
    rule = notification_service.get_rule(db, rule_id)
    return RuleListItem.model_validate(rule)


@router.patch(
    "/rules/{rule_id}",
    response_model=RuleListItem,
    summary="更新规则(全字段可选)",
)
def update_rule(
    rule_id: int,
    payload: RulePatchRequest,
    db: DBSession,
    _user: CurrentUser,
) -> RuleListItem:
    """🔒"""
    rule = notification_service.update_rule(db, rule_id, patch=payload)
    db.commit()
    db.refresh(rule)
    return RuleListItem.model_validate(rule)


@router.delete(
    "/rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除规则",
)
def delete_rule(
    rule_id: int,
    response: Response,
    db: DBSession,
    _user: CurrentUser,
) -> Response:
    """🔒"""
    notification_service.delete_rule(db, rule_id)
    db.commit()
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post(
    "/rules/{rule_id}/preview",
    response_model=RulePreviewResponse,
    status_code=status.HTTP_200_OK,
    summary="用假数据渲染模板(不发送)",
)
def preview_rule(
    rule_id: int,
    db: DBSession,
    _user: CurrentUser,
) -> RulePreviewResponse:
    """🔒 调试模板用;返回 ``{ title, body }``,不真发送。"""
    title, body = notification_service.preview_rule(db, rule_id)
    return RulePreviewResponse(title=title, body=body)
