"""应用配置 — 从环境变量加载,启动时一次性。

详见 `进度/设计/后端架构.md` § 9.2、§ 5.1。
真实业务设置(retention_days / timezone / 等)走 DB 里的 `settings` 表,
不在这里 — 见 `app/services/settings_service.py`(待 Backend-Models agent 创建)。
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用启动期一次性配置。

    优先级:环境变量 > `.env` 文件 > 默认值。
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ===== 基础 =====
    app_name: str = "签到脚本聚合管理面板"
    environment: str = Field(
        default="production",
        description='"production" / "development" / "test"',
    )
    log_level: str = Field(default="INFO", description="DEBUG/INFO/WARNING/ERROR")
    tz: str = Field(
        default="Asia/Shanghai",
        description="默认时区(可被 DB settings 表覆盖)",
        alias="TZ",
    )

    # ===== Web =====
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = Field(default=1, description="必须 1,APScheduler 同进程模式禁止多 worker")
    #: audit High #9:expose_docs 默认值依 environment 推断 ——
    #: production → False(/openapi.json 与 /docs 返 404,屏蔽攻击面枚举)
    #: 其他(development/test)→ True
    #: 仍可被环境变量 ``EXPOSE_DOCS=true`` 显式覆盖(production 临时调试)
    expose_docs: bool | None = Field(
        default=None,
        description=(
            "是否暴露 /docs 与 /openapi.json。"
            "默认依 environment 推断 —— production 关闭,其他打开。"
            "可被环境变量 EXPOSE_DOCS=true|false 显式覆盖。"
        ),
    )

    def is_docs_exposed(self) -> bool:
        """安全策略:expose_docs 显式设置时听它的,否则按 environment 推断。

        audit High #9:历史默认 ``expose_docs=True``,生产 ``/openapi.json``
        无鉴权暴露全部 36 端点 schema。修复为"按 environment 推断"——
        production 默认关闭,显式可覆盖。
        """
        if self.expose_docs is not None:
            return bool(self.expose_docs)
        return not self.is_production

    # ===== 数据库 =====
    database_url: str = Field(
        default="sqlite:///./data/db.sqlite3",
        description="业务数据库",
    )
    scheduler_db_url: str = Field(
        default="sqlite:///./data/scheduler.db",
        description="APScheduler jobstore(独立 SQLite 避免锁竞争);"
        "v1 用 MemoryJobStore 时此项保留备用",
    )

    # ===== 加密 =====
    encryption_key_path: Path = Field(
        default=Path("./data/encryption.key"),
        description="Fernet 主密钥文件,首次启动若不存在则自动生成",
    )

    # ===== 路径 =====
    app_data_dir: Path = Field(
        default=Path("./data"),
        description="应用数据根目录(含 db / encryption.key / scripts data_dir)",
    )
    scripts_dir: Path = Field(
        default=Path("./scripts"),
        description="用户脚本插件目录(每个脚本一个子目录)",
    )
    logs_dir: Path = Field(
        default=Path("./logs"),
        description="应用日志目录",
    )

    # ===== Session(可被 DB settings.session_ttl_hours 覆盖)=====
    session_cookie_name: str = "sid"
    session_ttl_hours_default: int = 24

    # ===== CORS(开发用,生产同源时禁用)=====
    dev_cors_origins: list[str] = Field(
        default_factory=list,
        description="开发环境允许的 CORS origin 白名单;生产应为空",
    )

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        return self.environment == "development"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """单例 settings,启动时计算一次。"""
    return Settings()  # type: ignore[call-arg]
