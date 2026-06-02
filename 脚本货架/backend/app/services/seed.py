"""种子导入：把 ``seed_dir/<slug>/`` 幂等导入货架（首启 / install 调用）。"""
from __future__ import annotations

from pathlib import Path

from loguru import logger
from sqlalchemy import select

from app.config import get_settings
from app.db.models.script import HubScript
from app.db.session import SessionLocal
from app.services import script_store


def seed_initial_scripts() -> int:
    """遍历种子目录，未入库的脚本导入货架。返回新导入数量（幂等）。"""
    settings = get_settings()
    seed_dir = Path(settings.seed_dir).resolve()
    if not seed_dir.is_dir():
        return 0

    n = 0
    with SessionLocal() as db:
        for child in sorted(seed_dir.iterdir()):
            if not child.is_dir() or not (child / "manifest.yaml").is_file():
                continue
            existing = db.execute(
                select(HubScript).where(HubScript.slug == child.name)
            ).scalar_one_or_none()
            if existing:
                continue
            try:
                script_store.import_from_dir(db, child, force=False)
                db.commit()
                n += 1
                logger.info("种子导入 {}", child.name)
            except Exception as exc:  # noqa: BLE001 — 单个种子失败不应阻断启动
                db.rollback()
                logger.warning("种子 {} 导入失败: {}", child.name, exc)
    return n
