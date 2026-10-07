import enum
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.models import Author, Book, Genre, Role, User
from app.models.user_book_relations import Rating


class StatsRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _count_by(self, column: InstrumentedAttribute) -> dict[str, int]:
        rows = (await self.session.execute(
            select(column, func.count()).group_by(column)
        )).all()
        return {(k.value if isinstance(k, enum.Enum) else str(k)): n for k, n in rows}

    async def books_by_status(self) -> dict[str, int]:
        return await self._count_by(Book.status)

    async def books_by_access_type(self) -> dict[str, int]:
        return await self._count_by(Book.access_type)

    async def users_by_status(self) -> dict[str, int]:
        return await self._count_by(User.status)

    async def users_by_role(self) -> dict[str, int]:
        rows = (await self.session.execute(
            select(Role.name, func.count(User.id))
            .select_from(User).join(Role, User.role_id == Role.id)
            .group_by(Role.name)
        )).all()
        return {k.value: n for k, n in rows}

    async def count_authors(self) -> int:
        return (await self.session.execute(select(func.count()).select_from(Author))).scalar_one()

    async def count_genres(self) -> int:
        return (await self.session.execute(select(func.count()).select_from(Genre))).scalar_one()

    async def ratings_overall(self) -> tuple[int, Decimal | None]:
        row = (await self.session.execute(
            select(func.count(Rating.id), func.avg(Rating.score))
        )).one()
        return row[0], row[1]