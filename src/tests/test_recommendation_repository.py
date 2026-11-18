from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlalchemy.dialects import postgresql

from app.models import BookStatus
from app.repositories.recommendation_repo import RecommendationRepository


async def test_snapshot_maps_statuses_genres_and_reading_exclusions_without_book_text():
    published = SimpleNamespace(id=1, title="First", description="Description", status=BookStatus.PUBLISHED,
                                genres=[SimpleNamespace(name="z"), SimpleNamespace(name="a")])
    archived = SimpleNamespace(id=2, title="Second", description="Old", status=BookStatus.ARCHIVED, genres=[])
    result = lambda rows: SimpleNamespace(all=lambda: rows)
    session = SimpleNamespace(
        scalars=AsyncMock(side_effect=[result([published, archived]), result(["a"]), result([2, 1])]),
        execute=AsyncMock(return_value=result([SimpleNamespace(user_id=7, book_id=2, score=9)])),
    )
    data = await RecommendationRepository(session).load(7)
    assert data.books[0].published and not data.books[1].published
    assert data.books[0].genres == ("a", "z")
    assert data.ratings[0].book_id == 2
    assert data.interests == ["a"] and data.excluded == [1, 2]
    queries = [str(call.args[0].compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
               for call in session.scalars.await_args_list]
    assert "text_content" not in queries[0]
    assert "DRAFT" in queries[0]
    assert "finished_at IS NOT NULL" in queries[2]
    assert "RETURNED" in queries[2] and "UNION" in queries[2]
