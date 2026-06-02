"""脚本货架 — 应用配置（环境变量加载，启动期一次性）。

精简自主项目 ``backend/app/config.py``：去掉加密 / 调度器 / 多 worker 相关。
货架只存脚本源码 + 元数据（非敏感），无需 Fernet 主密钥。
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用启动期一次性配置。优先级：环境变量 > ``.env`` > 默认值。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ===== 基础 =====
    app_name: str = "脚本货架"
    environment: str = Field(default="production", description='"production"/"development"/"test"')
    log_level: str = Field(default="INFO")
    tz: str = Field(default="Asia/Shanghai", alias="TZ")

    # ===== Web =====
    host: str = "0.0.0.0"
    port: int = 8000
    #: 是否暴露 /docs 与 /openapi.json；None 依 environment（production 关）。
    expose_docs: bool | None = Field(default=None)

    # ===== 数据库 =====
    database_url: str = Field(default="sqlite:///./data/hub.sqlite3")

    # ===== 路径 =====
    app_data_dir: Path = Field(default=Path("./data"))
    #: 货架脚本源目录（每脚本一子目录，结构同管家 scripts/）。compute_script_bundle 的根。
    scripts_dir: Path = Field(default=Path("./data/scripts"))
    #: 初始库存种子目录（入 git，启动时幂等导入）。
    seed_dir: Path = Field(default=Path("./seed/scripts"))
    logs_dir: Path = Field(default=Path("./logs"))

    # ===== Session =====
    session_cookie_name: str = "hub_sid"
    session_ttl_hours_default: int = 24
    #: cookie Secure 标志；None 依 environment；纯 HTTP/IP 部署设 false。
    cookie_secure: bool | None = Field(default=None)

    # ===== CORS（M3：允许管家前端直读货架列表，逗号分隔）=====
    cors_origins: str = Field(default="", description="逗号分隔的 CORS origin 白名单")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def effective_cookie_secure(self) -> bool:
        """cookie Secure：显式 cookie_secure 听它的，否则按 is_production。"""
        if self.cookie_secure is not None:
            return bool(self.cookie_secure)
        return self.is_production

    def is_docs_exposed(self) -> bool:
        if self.expose_docs is not None:
            return bool(self.expose_docs)
        return not self.is_production


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """单例 settings，启动时计算一次。"""
    return Settings()  # type: ignore[call-arg]
