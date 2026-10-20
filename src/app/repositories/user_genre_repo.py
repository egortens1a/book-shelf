from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UserGenre


class UserGenreRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_genre_ids(self, user_id: int) -> list[int]:
        result = await self.session.scalars(
            select(UserGenre.genre_id)
            .where(UserGenre.user_id == user_id)
            .order_by(UserGenre.genre_id)
        )
        return list(result.all())

    async def replace(self, user_id: int, genre_ids: list[int]) -> None:
        wanted = set(genre_ids)
        rows = (
            await self.session.scalars(select(UserGenre).where(UserGenre.user_id == user_id))
        ).all()
        current = {row.genre_id for row in rows}

        for row in rows:
            if row.genre_id not in wanted:
                await self.session.delete(row)
        self.session.add_all(
            UserGenre(user_id=user_id, genre_id=g) for g in sorted(wanted - current)
        )
        await self.session.flush()