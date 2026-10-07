from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user_book_relations import ReadingProgress


class ReadingProgressRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create(self, user_id: int, book_id: int) -> ReadingProgress:
        await self.session.execute(
            pg_insert(ReadingProgress)
            .values(user_id=user_id, book_id=book_id, position=0)
            .on_conflict_do_nothing(
                index_elements=[ReadingProgress.user_id, ReadingProgress.book_id]
            )
        )
        result = await self.session.execute(
            select(ReadingProgress).where(
                ReadingProgress.user_id == user_id,
                ReadingProgress.book_id == book_id
            )
        )
        return result.scalar_one()

    async def update_position(
        self, user_id: int, book_id: int, position: int, finished_at: datetime | None = None
    ) -> ReadingProgress:
        progress = await self.get_or_create(user_id, book_id)
        progress.position = position
        if finished_at is not None:
            progress.finished_at = finished_at
        await self.session.flush()
        await self.session.refresh(progress)
        return progress

    async def get(self, user_id: int, book_id: int) -> ReadingProgress | None:
        result = await self.session.execute(
            select(ReadingProgress).where(
                ReadingProgress.user_id == user_id,
                ReadingProgress.book_id == book_id
            )
        )
        return result.scalar_one_or_none()