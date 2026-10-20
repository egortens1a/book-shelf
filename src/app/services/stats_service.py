from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RoleTypes
from app.repositories import StatsRepository
from app.services.base import BaseService

from app.models import Book


class StatsService(BaseService):
    def __init__(self, session: AsyncSession):
        super().__init__(session)
        self.stats_repo = StatsRepository(session)

    async def get_catalog_stats(self, actor_id: int) -> dict[str, Any]:
        await self._require_role(actor_id, RoleTypes.ADMIN)
        ratings_count, ratings_avg = await self.stats_repo.ratings_overall()
        return {
            "books_by_status": await self.stats_repo.books_by_status(),
            "books_by_access_type": await self.stats_repo.books_by_access_type(),
            "authors_total": await self.stats_repo.count_authors(),
            "genres_total": await self.stats_repo.count_genres(),
            "users_by_role": await self.stats_repo.users_by_role(),
            "users_by_status": await self.stats_repo.users_by_status(),
            "ratings_count": ratings_count,
            "ratings_average": round(float(ratings_avg), 2) if ratings_avg is not None else None,
            # README требует статистику «по каталогу, выдачам и подпискам»,
            # поэтому одного каталога с пользователями недостаточно.
            "reservations_by_status": await self.stats_repo.reservations_by_status(),
            "subscriptions_by_status": await self.stats_repo.subscriptions_by_status(),
            "fines_by_status": await self.stats_repo.fines_by_status(),
            "unpaid_fines_total": await self.stats_repo.unpaid_fines_total(),
        }
        
    async def top_k_book_by_genre(self, k: int, genre_id: int) -> list[tuple[str, float, int]]:
        return await self.stats_repo.get_top_by_genre(
            genre_id=genre_id, limit=k
        )