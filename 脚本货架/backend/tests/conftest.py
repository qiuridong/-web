"""货架后端测试配置：临时 DB + scripts_dir + 种子，与生产数据完全隔离。

⚠️ 必须在 import app 之前设置环境变量（config 用 lru_cache，启动期一次性读取）。
"""
import os
import tempfile
from pathlib import Path

import pytest

_TMP = tempfile.mkdtemp(prefix="hub_test_")
_BACKEND = Path(__file__).resolve().parents[1]  # 脚本货架/backend

os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/test.sqlite3"
os.environ["APP_DATA_DIR"] = _TMP
os.environ["SCRIPTS_DIR"] = f"{_TMP}/scripts"
os.environ["SEED_DIR"] = str(_BACKEND / "seed" / "scripts")  # 用真种子做断言基准
os.environ["LOGS_DIR"] = f"{_TMP}/logs"
os.environ["PYTHONIOENCODING"] = "utf-8"

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    """模块级 TestClient；with 触发 lifespan（建表 + 种子导入）。"""
    with TestClient(app) as c:
        yield c
