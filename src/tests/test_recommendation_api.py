from unittest.mock import AsyncMock

import httpx
import pytest

from app.api.deps import get_async_session
from app.core.config import get_settings
from app.core.security import create_access_token
from app.main import create_app
from app.models import RoleTypes, User, UserStatus
from app.repositories.recommendation_repo import RecommendationRepository
from app.repositories.user_repo import UserRepository


@pytest.fixture
def api(monkeypatch, snapshot, grpc_target):
    app = create_app()

    async def session():
        yield None

    app.dependency_overrides[get_async_session] = session
    monkeypatch.setattr(get_settings(), "recommendations_grpc_target", grpc_target)
    user = User(id=1, role_id=1, full_name="Test reader", email="test@example.com", status=UserStatus.ACTIVE)
    monkeypatch.setattr(UserRepository, "get_by_id", AsyncMock(return_value=user))
    monkeypatch.setattr(UserRepository, "get_role_name", AsyncMock(return_value=RoleTypes.READER))
    loader = AsyncMock(return_value=snapshot)
    monkeypatch.setattr(RecommendationRepository, "load", loader)
    return app, loader, user


def headers():
    return {"Authorization": "Bearer " + create_access_token(1, 1)}


async def test_http_to_real_grpc_preserves_contract_and_token_identity(api, snapshot):
    app, loader, _ = api
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/me/recommendations?user_id=999", headers=headers())
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 10
    assert all(set(i) == {"book_id", "title", "score"} for i in items)
    titles = {book.book_id: book.title for book in snapshot.books}
    assert all(item["title"] == titles[item["book_id"]] for item in items)
    assert not {1, 2, 3} & {i["book_id"] for i in items}
    loader.assert_awaited_once_with(1)


@pytest.mark.parametrize("limit,expected", [(1, 200), (100, 200), (0, 422), (101, 422)])
async def test_limit_validation(api, limit, expected):
    app, _, _ = api
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/me/recommendations?limit={limit}", headers=headers())
    assert response.status_code == expected
    if expected == 200:
        assert len(response.json()["items"]) <= limit


async def test_no_token_returns_401_before_rpc(api):
    app, loader, _ = api
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/me/recommendations")
    assert response.status_code == 401
    loader.assert_not_awaited()


async def test_empty_catalog_returns_empty_items_through_rpc(api, snapshot):
    app, _, _ = api
    snapshot.books.clear()
    snapshot.ratings.clear()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/me/recommendations", headers=headers())
    assert response.status_code == 200
    assert response.json() == {"items": []}


@pytest.mark.parametrize("role", [RoleTypes.ADMIN, RoleTypes.LIBRARIAN])
async def test_other_roles_return_403_before_rpc(api, monkeypatch, role):
    app, loader, _ = api
    monkeypatch.setattr(UserRepository, "get_role_name", AsyncMock(return_value=role))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/me/recommendations", headers=headers())
    assert response.status_code == 403
    loader.assert_not_awaited()


async def test_blocked_user_returns_403_before_rpc(api):
    app, loader, user = api
    user.status = UserStatus.BLOCKED
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/me/recommendations", headers=headers())
    assert response.status_code == 403
    loader.assert_not_awaited()


async def test_unavailable_rpc_returns_503(api, monkeypatch):
    from app.core.errors import RecommendationsUnavailable
    from app.services.recommendation_client import RecommendationClient

    app, _, _ = api
    monkeypatch.setattr(RecommendationClient, "recommend", AsyncMock(side_effect=RecommendationsUnavailable("unavailable")))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/me/recommendations", headers=headers())
    assert response.status_code == 503
    assert response.json() == {"detail": "unavailable"}
