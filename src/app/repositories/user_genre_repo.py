from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import UserGenre


class UserGenreRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_genre_ids(self, user_id: int) -> list[int]:
        result = await self.session.execute(
            select(UserGenre.genre_id)
            .where(UserGenre.user_id == user_id)
            .order_by(UserGenre.genre_id)
        )
        return list(result.scalars().all())

    async def replace(self, user_id: int, genre_ids: list[int]) -> None:
        wanted = set(genre_ids)
        current = set(await self.get_genre_ids(user_id))

        stale = current - wanted
        if stale:
            await self.session.execute(
                delete(UserGenre).where(
                    UserGenre.user_id == user_id, UserGenre.genre_id.in_(stale)
                )
            )
        missing = wanted - current
        if missing:
            await self.session.execute(
                pg_insert(UserGenre)
                .values([{"user_id": user_id, "genre_id": g} for g in sorted(missing)])
                .on_conflict_do_nothing(index_elements=[UserGenre.user_id, UserGenre.genre_id])
            )