"""FastAPI 通用依赖注入。

详见 `进度/设计/后端架构.md` § 6.1。
"""
from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Annotated

from fastapi import Cookie, Depends, Query, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_db

if TYPE_CHECKING:
    from app.scheduler.engine import SchedulerService


# ============================================================
# DB Session
# ============================================================
def get_db_session() -> Iterator[Session]:
    """重新导出 `get_db` 作为依赖入口,便于路由层 import 一处。"""
    yield from get_db()


DBSession = Annotated[Session, Depends(get_db_session)]


# ============================================================
# Current User
# ============================================================
def _get_session_cookie_name() -> str:
    return get_settings().session_cookie_name


def get_current_user(
    request: Request,
    db: DBSession,
) -> object:
    """获取当前登录用户。

    实现:
    1. 从 cookie 取 `settings.session_cookie_name`(默认 `sid`)
    2. 调 `auth_service.verify_session(db, token)`
    3. 失败抛 `app.core.exceptions.SessionExpired`(由 error_handler 转 401)
    4. 顺便把 user 缓存到 `request.state.user`,供 SSE 等场景复用

    返回:`app.db.models.user.User`(运行时类型)
    """
    # 局部 import 避免循环依赖(deps → services → models → ... → deps)
    from app.services import auth_service

    cookie_name = _get_session_cookie_name()
    token = request.cookies.get(cookie_name)
    user = auth_service.verify_session(db, token)

    # 缓存到 request.state 供下游使用
    request.state.user = user
    request.state.session_token = token
    return user


# 显式注解为 object,避免 deps 模块对 User 模型循环依赖(运行时仍是 User)
CurrentUser = Annotated[object, Depends(get_current_user)]


def get_optional_session_token(
    request: Request,
) -> str | None:
    """从 cookie 取 token(可能为空),不校验合法性。

    用途:`/auth/change-password` 成功后撤销其他 session 时需要知道当前 token。
    """
    return request.cookies.get(_get_session_cookie_name())


OptionalSessionToken = Annotated[str | None, Depends(get_optional_session_token)]


# ============================================================
# 分页参数
# ============================================================
def get_pagination(
    page: Annotated[int, Query(ge=1, description="页码,从 1 起")] = 1,
    page_size: Annotated[
        int,
        Query(ge=1, le=200, description="每页条数,1-200"),
    ] = 20,
) -> tuple[int, int]:
    """统一分页依赖。

    返回 `(page, page_size)`,service 层用 `(page-1) * page_size` 算 offset。

    最大 200 条/页是 § 2 约定的硬上限,防止前端误传 10000 拖垮 SQLite。
    """
    return page, page_size


Pagination = Annotated[tuple[int, int], Depends(get_pagination)]


# ============================================================
# Scheduler
# ============================================================
def get_scheduler(request: Request) -> "SchedulerService":
    """从 ``app.state.scheduler`` 取调度器实例。

    若未启动(测试 / 关停期)抛 RuntimeError;路由层应捕获或交给全局
    error_handler。
    """
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is None:
        raise RuntimeError("Scheduler 尚未初始化")
    return scheduler


def get_scheduler_service() -> "SchedulerService":
    """模块级 fallback 取调度器(供 APScheduler job 回调用,没有 Request)。

    从 ``app.state.scheduler`` 不可达时回退到 module 级单例。
    """
    # 尝试通过 module 内全局拿(由 main.py lifespan 设置)
    from app.main import get_app_scheduler  # noqa: PLC0415

    return get_app_scheduler()


# 类型注解(供路由使用 ``Annotated[..., Depends(get_scheduler)]``)
SchedulerDep = Annotated[object, Depends(get_scheduler)]
