from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_book_relations import Rating


class RatingRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_or_update(
        self, user_id: int, book_id: int, score: int, comment: str | None = None
    ) -> Rating:
        rating = await self.get_by_user_and_book(user_id, book_id)
        if rating is None:
            rating = Rating(user_id=user_id, book_id=book_id, score=score, comment=comment)
            self.session.add(rating)
        else:
            rating.score = score
            rating.comment = comment
        await self.session.flush()
        await self.session.refresh(rating)
        return rating

    async def delete(self, user_id: int, book_id: int) -> None:
        await self.session.execute(
            delete(Rating).where(Rating.user_id == user_id, Rating.book_id == book_id)
        )

    async def get_by_user_and_book(self, user_id: int, book_id: int) -> Rating | None:
        return await self.session.scalar(
            select(Rating).where(Rating.user_id == user_id, Rating.book_id == book_id)
        )

    async def get_summary(self, book_id: int) -> tuple[int, Decimal | None]:
        count, avg = (
            await self.session.execute(
                select(func.count(Rating.id), func.avg(Rating.score)).where(
                    Rating.book_id == book_id
                )
            )
        ).one()
        return count, avg

    async def list_by_book(
        self, book_id: int, limit: int = 50, offset: int = 0
    ) -> list[Rating]:
        result = await self.session.scalars(
            select(Rating)
            .where(Rating.book_id == book_id)
            .order_by(Rating.created_at.desc(), Rating.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.all())