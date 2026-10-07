from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user_book_relations import Rating


class RatingRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_or_update(self, user_id: int, book_id: int, score: int, comment: str | None = None) -> Rating:
        stmt = pg_insert(Rating).values(
            user_id=user_id, book_id=book_id, score=score, comment=comment
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[Rating.user_id, Rating.book_id],
            set_={"score": stmt.excluded.score, "comment": stmt.excluded.comment},
        ).returning(Rating)
        result = await self.session.execute(stmt, execution_options={"populate_existing": True})
        return result.scalar_one()

    async def delete(self, user_id: int, book_id: int) -> None:
        await self.session.execute(
            delete(Rating).where(
                Rating.user_id == user_id,
                Rating.book_id == book_id
            )
        )

    async def get_by_user_and_book(self, user_id: int, book_id: int) -> Rating | None:
        result = await self.session.execute(
            select(Rating).where(
                Rating.user_id == user_id,
                Rating.book_id == book_id
            )
        )
        return result.scalar_one_or_none()

    async def get_summary(self, book_id: int) -> tuple[int, Decimal | None]:
        row = (await self.session.execute(
            select(func.count(Rating.id), func.avg(Rating.score)).where(Rating.book_id == book_id)
        )).one()
        return row[0], row[1]

    async def list_by_book(self, book_id: int, limit: int = 50, offset: int = 0) -> list[Rating]:
        result = await self.session.execute(
            select(Rating).where(Rating.book_id == book_id)
            .order_by(Rating.created_at.desc(), Rating.id.desc())
            .limit(limit).offset(offset)
        )
        return list(result.scalars().all())