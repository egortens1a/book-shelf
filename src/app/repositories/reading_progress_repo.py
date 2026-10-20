from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_book_relations import ReadingProgress


class ReadingProgressRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, user_id: int, book_id: int) -> ReadingProgress | None:
        return await self.session.scalar(
            select(ReadingProgress).where(
                ReadingProgress.user_id == user_id,
                ReadingProgress.book_id == book_id,
            )
        )

    async def get_or_create(self, user_id: int, book_id: int) -> ReadingProgress:
        """Запись прогресса, создаётся при первом обращении.

        Вставка с разрешением конфликта: два параллельных сохранения позиции
        не подерутся за uq_readingprogress_user_book. Проверка перед вставкой
        оставляла окно между SELECT и INSERT.
        """
        await self.session.execute(
            pg_insert(ReadingProgress)
            .values(user_id=user_id, book_id=book_id, position=0)
            .on_conflict_do_nothing(
                index_elements=[ReadingProgress.user_id, ReadingProgress.book_id]
            )
        )
        progress = await self.get(user_id, book_id)
        assert progress is not None  # строка либо вставлена нами, либо уже была
        return progress

    async def update_position(
        self,
        user_id: int,
        book_id: int,
        position: int,
        finished_at: datetime | None = None,
    ) -> ReadingProgress:
        """Сохраняет позицию чтения.

        Отметка о прочтении выставляется только один раз: если книга уже
        дочитана, повторное достижение конца текста её не перезаписывает,
        а возврат к середине не сбрасывает.
        """
        progress = await self.get_or_create(user_id, book_id)
        progress.position = position
        if finished_at is not None and progress.finished_at is None:
            progress.finished_at = finished_at
        await self.session.flush()
        await self.session.refresh(progress)
        return progress
