"""Опциональный HTTP -> gRPC тест отдельного процесса с настоящей ONNX-моделью.

BOOKSHELF_TEST_MODEL=1 python -m pytest src/tests/test_recommendation_process.py -q
Требует уже скачанную модель; сеть для загрузки запрещена через HF_HUB_OFFLINE.
БД подменена тестовым снимком, JWT и HTTP/gRPC-вызовы настоящие.
"""

import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
from unittest.mock import AsyncMock

import grpc
import httpx
import pytest

from app.core.config import get_settings
from app.core.db import get_async_session
from app.core.security import create_access_token
from app.main import create_app
from app.models import RoleTypes, User, UserStatus
from app.repositories.recommendation_repo import RecommendationRepository
from app.repositories.user_repo import UserRepository


@pytest.mark.skipif(os.getenv("BOOKSHELF_TEST_MODEL") != "1", reason="Opt-in: requires cached ONNX weights")
async def test_http_calls_separate_process_with_real_embeddings(monkeypatch, snapshot):
    root = Path(__file__).resolve().parents[2]
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    target = f"127.0.0.1:{port}"
    env = dict(os.environ, HF_HUB_OFFLINE="1", PYTHONPATH=str(root / "src"),
               RECOMMENDATIONS_HOST="127.0.0.1", RECOMMENDATIONS_PORT=str(port),
               RECOMMENDATIONS_CACHE_DIR=str(root / ".cache/models"))
    log_dir = root / ".cache/test-runs"
    log_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".log", dir=log_dir, delete=False) as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "recsys.server"],
            cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    try:
        with grpc.insecure_channel(target) as channel:
            grpc.channel_ready_future(channel).result(timeout=45)
        monkeypatch.setattr(get_settings(), "recommendations_grpc_target", target)
        monkeypatch.setattr(UserRepository, "get_by_id", AsyncMock(return_value=User(id=1, role_id=1, status=UserStatus.ACTIVE)))
        monkeypatch.setattr(UserRepository, "get_role_name", AsyncMock(return_value=RoleTypes.READER))
        monkeypatch.setattr(RecommendationRepository, "load", AsyncMock(return_value=snapshot))

        async def session():
            yield None

        app = create_app()
        app.dependency_overrides[get_async_session] = session
        token = create_access_token(1, 1)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/me/recommendations", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200, response.text
        assert len(response.json()["items"]) == 10
        assert not {1, 2, 3} & {item["book_id"] for item in response.json()["items"]}
        assert process.pid != os.getpid()
        assert "gRPC Recommend" in Path(log.name).read_text(encoding="utf-8")
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
