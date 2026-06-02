"""鉴权相关 schema。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class SetupRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    display_name: str | None = None


class UserResponse(BaseModel):
    id: int
    username: str
    display_name: str | None = None
    is_admin: bool


class SetupStateResponse(BaseModel):
    setup_required: bool


class MessageResponse(BaseModel):
    message: str = "ok"
