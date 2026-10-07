from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AccessType, Book, BookStatus
from app.models.user_book_relations import ReadingProgress
from app.repositories import BookRepository, ReadingProgressRepository
from app.services.base import BaseService
from app.services.protocols import SubscriptionChecker


class ReadingService(BaseService):
    def __init__(
        self, session: AsyncSession,
        subscription_checker: SubscriptionChecker
    ):
        super().__init__(session)
        self.book_repo = BookRepository(session)
        self.progress_repo = ReadingProgressRepository(session)
        self.subscription_checker = subscription_checker

    async def _get_readable_book(self, user_id: int, book_id: int) -> Book:
        """Книга, которую этот читатель вправе читать сейчас, иначе ValueError."""
        book = await self.book_repo.get_by_id(book_id)
        if book is None or book.status == BookStatus.DRAFT:
            raise ValueError("Книга не найдена")
        if book.access_type == AccessType.NONE:
            raise ValueError("У книги нет электронной версии")
        if book.status == BookStatus.ARCHIVED:
            # архивная книга остаётся только тем, кто уже её читает
            if await self.progress_repo.get(user_id, book_id) is None:
                raise ValueError("Книга в архиве и недоступна для нового чтения")
        if book.access_type == AccessType.SUBSCRIPTION:
            if self.subscription_checker is None:
                raise RuntimeError("Не передан subscription_checker")
            if not await self.subscription_checker(user_id):
                raise ValueError("Для этой книги нужна активная подписка")
        return book

    async def open_for_reading(self, user_id: int, book_id: int) -> tuple[str, int]:
        """Текст книги и позиция, с которой читатель продолжит"""
        await self._get_readable_book(user_id, book_id)
        text = await self.book_repo.get_text_content(book_id)
        progress = await self.progress_repo.get(user_id, book_id)
        return text or "", progress.position if progress else 0

    async def save_position(self, user_id: int, book_id: int, position: int) -> ReadingProgress:
        await self._get_readable_book(user_id, book_id)
        length = await self.book_repo.get_text_length(book_id) or 0
        if not 0 <= position <= length:
            raise ValueError(f"Позиция должна быть в пределах текста: от 0 до {length}")

        # finished_at ставится, когда позиция достигла конца текста; повторно не сбрасывается
        finished_at = datetime.now(timezone.utc) if position == length else None
        async with self._transaction():
            progress = await self.progress_repo.update_position(
                user_id, book_id, position, finished_at
            )
        return progress

    async def get_progress(self, user_id: int, book_id: int) -> ReadingProgress | None:
        return await self.progress_repo.get(user_id, book_id)