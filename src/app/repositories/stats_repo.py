import enum
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.models import Author, Book, BookStatus, Genre, Rating, Role, User


class StatsRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _count_by(self, column: InstrumentedAttribute) -> dict[str, int]:
        rows = (
            await self.session.execute(select(column, func.count()).group_by(column))
        ).all()
        return {(k.value if isinstance(k, enum.Enum) else str(k)): n for k, n in rows}

    async def books_by_status(self) -> dict[str, int]:
        return await self._count_by(Book.status)

    async def books_by_access_type(self) -> dict[str, int]:
        return await self._count_by(Book.access_type)

    async def users_by_status(self) -> dict[str, int]:
        return await self._count_by(User.status)

    async def users_by_role(self) -> dict[str, int]:
        rows = (
            await self.session.execute(
                select(Role.name, func.count(User.id))
                .join(Role, User.role_id == Role.id)
                .group_by(Role.name)
            )
        ).all()
        return {k.value: n for k, n in rows}

    async def count_authors(self) -> int | None:
        return await self.session.scalar(select(func.count(Author.id)))

    async def count_genres(self) -> int | None:
        return await self.session.scalar(select(func.count(Genre.id)))

    async def ratings_overall(self) -> tuple[int, Decimal | None]:
        count, avg = (
            await self.session.execute(select(func.count(Rating.id), func.avg(Rating.score)))
        ).one()
        return count, avg

    async def get_top_by_genre(
        self, genre_id: int, limit: int = 10
    ) -> list[tuple[str, float, int]]:
        avg_score = func.avg(Rating.score)
        ratings_count = func.count(Rating.id)

        rows = await self.session.execute(
            select(Book.title, avg_score, ratings_count)
            .join(Rating, Rating.book_id == Book.id)
            .where(
                Book.status == BookStatus.PUBLISHED,
                Book.genres.any(Genre.id == genre_id),
            )
            .group_by(Book.id, Book.title)
            .order_by(avg_score.desc(), ratings_count.desc(), Book.id)
            .limit(limit)
        )
        return [(title, float(avg), cnt) for title, avg, cnt in rows.all()]