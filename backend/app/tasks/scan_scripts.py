"""周期扫描 ``scripts/`` 目录 — APScheduler 周期任务回调。

实现见 `进度/设计/后端架构.md` § 1.8(``script_scan_interval_sec``)。

策略:
- 每 ``settings.script_scan_interval_sec`` 秒(默认 300)扫一次
- 扫到 added/updated/removed 则写应用日志,通常静默
- 异常不抛(避免污染 scheduler 日志);记 warning 即可
"""
from __future__ import annotations

from loguru import logger

from app.config import get_settings
from app.db.session import SessionLocal
from app.services import script_service


def scan_scripts_job() -> None:
    """每 N 秒被 APScheduler 调用。"""
    settings = get_settings()
    scripts_dir = settings.scripts_dir.resolve()

    try:
        with SessionLocal() as db:
            result = script_service.scan_all(db, scripts_dir)
            db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("scan_scripts_job 失败: {}", exc)
        return

    if (
        result["added"]
        or result["updated"]
        or result["removed"]
        or result["errors"]
    ):
        logger.info(
            "周期扫描完成 added={} updated={} removed={} errors={}",
            len(result["added"]),
            len(result["updated"]),
            len(result["removed"]),
            len(result["errors"]),
        )
