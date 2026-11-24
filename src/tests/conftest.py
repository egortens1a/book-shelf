"""Изолированные настройки: тесты не подключаются к пользовательской БД."""

import os

import numpy as np
import pytest

os.environ.update({
    "DATABASE_URL": "postgresql+asyncpg://test:test@127.0.0.1:1/test",
    "JWT_SECRET_KEY": "bookshelf-test-secret-with-at-least-32-characters",
    "RESERVATION_HOURS": "48", "LOAN_DAYS": "14", "MAX_ACTIVE_RESERVATIONS": "3",
    "FINE_PER_DAY": "50", "FINE_LOST": "1500", "SUBSCRIPTION_PRICE": "299",
})


class ToyEncoder:
    def encode(self, texts):
        return np.array([[1, 0] if "space" in t.lower() else [0, 1] for t in texts], dtype=np.float32)


@pytest.fixture
def grpc_target():
    from recsys.server import create_server

    server, port = create_server(ToyEncoder(), "127.0.0.1:0")
    server.start()
    try:
        yield f"127.0.0.1:{port}"
    finally:
        server.stop(grace=0).wait()


@pytest.fixture
def snapshot():
    from app.repositories.recommendation_repo import RecommendationData
    from recsys.domain import Book, Rating

    return RecommendationData(
        books=[Book(i, f"space {i}", "A book about space", ("science fiction",), i != 3)
               for i in range(1, 16)],
        ratings=[Rating(1, 1, 10)], interests=["space"], excluded=[2],
    )
