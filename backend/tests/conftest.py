"""pytest 共享 fixtures。

骨架阶段:仅提供一个 `client` fixture,后续各 agent 按需扩展(临时 DB / 临时密钥 / 模拟时钟等)。
"""
from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def app_factory():
    """延迟 import,避免在收集阶段触发 settings 加载。

    TODO(各 agent): 如需测试用 DB / 密钥隔离,在此 fixture 里覆写
    `app.config.get_settings` 后再 import `app.main.create_app`。
    """
    from app.main import create_app

    return create_app


@pytest.fixture()
def client(app_factory) -> Iterator[TestClient]:
    """同步 TestClient — 适合非 SSE 端点。

    SSE 端点(`/runs/{id}/logs/stream`)需用 `httpx.AsyncClient` + 手动迭代,
    见 `tests/test_api/test_sse.py`(待 Backend-SSE agent 创建)。
    """
    app = app_factory()
    with TestClient(app) as c:
        yield c


# TODO(Batch 2 / Backend-Models): 添加临时 SQLite DB fixture
#   @pytest.fixture()
#   def db_session() -> Iterator[Session]:
#       engine = create_engine("sqlite:///:memory:")
#       Base.metadata.create_all(engine)
#       ...

# TODO(Batch 2 / Backend-Auth): 添加临时 Fernet 密钥 fixture
#   @pytest.fixture(autouse=True)
#   def isolated_cipher(tmp_path, monkeypatch) -> None:
#       monkeypatch.setattr(...)
#       reset_cipher()
