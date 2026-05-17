"""鉴权 schemas — Pydantic v2。

实现见 `进度/设计/后端架构.md` § 2.1 / § 5.3。

模型清单:
- SetupStatusResponse(needs_setup: bool)
- SetupRequest(username, password, display_name?)
- LoginRequest(username, password)
- LoginResponse(user: UserResponse)
- UserResponse(id, username, display_name, is_admin, last_login_at)
- ChangePasswordRequest(old_password, new_password)
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ============================================================
# 共用约束
# ============================================================
USERNAME_MIN = 1
USERNAME_MAX = 64
PASSWORD_MIN = 8
PASSWORD_MAX = 128
DISPLAY_NAME_MAX = 64


def _normalize_username(v: str) -> str:
    """统一去首尾空白;空串保留供 min_length 校验报错。"""
    return v.strip()


# ============================================================
# Setup
# ============================================================
class SetupStatusResponse(BaseModel):
    """`GET /auth/setup-status` 响应。"""

    needs_setup: bool = Field(
        ...,
        description='users 表为空时为 true,前端跳「首次设置密码」页',
    )


class SetupRequest(BaseModel):
    """`POST /auth/setup` 请求体。"""

    model_config = ConfigDict(str_strip_whitespace=False)  # password 不剥空白

    username: str = Field(..., min_length=USERNAME_MIN, max_length=USERNAME_MAX)
    password: str = Field(..., min_length=PASSWORD_MIN, max_length=PASSWORD_MAX)
    display_name: str | None = Field(default=None, max_length=DISPLAY_NAME_MAX)

    @field_validator("username")
    @classmethod
    def _strip_username(cls, v: str) -> str:
        v = _normalize_username(v)
        if not v:
            raise ValueError("用户名不能为空")
        return v

    @field_validator("display_name")
    @classmethod
    def _strip_display_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


# ============================================================
# Login
# ============================================================
class LoginRequest(BaseModel):
    """`POST /auth/login` 请求体。"""

    model_config = ConfigDict(str_strip_whitespace=False)

    username: str = Field(..., min_length=USERNAME_MIN, max_length=USERNAME_MAX)
    password: str = Field(..., min_length=1, max_length=PASSWORD_MAX)

    @field_validator("username")
    @classmethod
    def _strip_username(cls, v: str) -> str:
        v = _normalize_username(v)
        if not v:
            raise ValueError("用户名不能为空")
        return v


class UserResponse(BaseModel):
    """`/auth/me`、`/auth/login` 等响应中的用户信息。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: str | None = None
    is_admin: bool = True
    last_login_at: datetime | None = None


class LoginResponse(BaseModel):
    """`POST /auth/login` 响应体。"""

    user: UserResponse


# ============================================================
# Change password
# ============================================================
class ChangePasswordRequest(BaseModel):
    """`POST /auth/change-password` 请求体。"""

    model_config = ConfigDict(str_strip_whitespace=False)

    old_password: str = Field(..., min_length=1, max_length=PASSWORD_MAX)
    new_password: str = Field(..., min_length=PASSWORD_MIN, max_length=PASSWORD_MAX)

    @field_validator("new_password")
    @classmethod
    def _validate_new_password(cls, v: str) -> str:
        # 与旧密码相同的判定放在 service 层(需要解 bcrypt),此处仅做基本格式
        if not v:
            raise ValueError("新密码不能为空")
        return v
