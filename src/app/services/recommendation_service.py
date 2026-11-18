"""Сборка снимка каталога и преобразование gRPC-ответа в HTTP DTO."""

import math

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import RecommendationsUnavailable
from app.repositories.recommendation_repo import RecommendationRepository
from app.schemas.recommendation import RecommendationRead, RecommendationsRead
from app.services.recommendation_client import RecommendationClient
from recsys.proto import recommendations_pb2 as pb


class RecommendationService:
    def __init__(self, session: AsyncSession, client: RecommendationClient):
        self.repo = RecommendationRepository(session)
        self.client = client

    async def recommend(self, user_id: int, limit: int = 10) -> RecommendationsRead:
        data = await self.repo.load(user_id)
        response = await self.client.recommend(pb.RecommendationRequest(
            user_id=user_id, limit=limit, interests=data.interests, excluded_book_ids=data.excluded,
            books=[pb.Book(book_id=b.book_id, title=b.title, description=b.description,
                           genres=b.genres, published=b.published) for b in data.books],
            ratings=[pb.Rating(user_id=r.user_id, book_id=r.book_id, score=r.score) for r in data.ratings],
        ))
        # Проверяем ответ и здесь: неизвестная/архивная/прочитанная книга не утекает в HTTP.
        excluded = set(data.excluded) | {r.book_id for r in data.ratings if r.user_id == user_id}
        allowed = {b.book_id: b for b in data.books if b.published and b.book_id not in excluded}
        seen = set()
        items = []
        for item in response.items:
            if item.book_id not in allowed or item.book_id in seen or not math.isfinite(item.score) or not 0 <= item.score <= 1:
                raise RecommendationsUnavailable("Invalid recommendation service response")
            seen.add(item.book_id)
            items.append(RecommendationRead(book_id=item.book_id, title=allowed[item.book_id].title, score=item.score))
        if len(items) > limit:
            raise RecommendationsUnavailable("Invalid recommendation service response")
        return RecommendationsRead(items=items)
