from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BookStatus
from app.models.user_book_relations import Rating
from app.repositories import BookRepository, RatingRepository, ReadingProgressRepository
from app.services.base import BaseService
from app.services.protocols import ReturnedBookChecker

MIN_SCORE, MAX_SCORE = 1, 10


@dataclass(frozen=True)
class RatingSummary:
    count: int
    average: float | None  # None, если оценок нет


class RatingService(BaseService):
    def __init__(
        self, session: AsyncSession,
        returned_book_checker: ReturnedBookChecker
    ):
        super().__init__(session)
        self.book_repo = BookRepository(session)
        self.rating_repo = RatingRepository(session)
        self.progress_repo = ReadingProgressRepository(session)
        self.returned_book_checker = returned_book_checker

    async def _has_finished(self, user_id: int, book_id: int) -> bool:
        progress = await self.progress_repo.get(user_id, book_id)
        if progress is not None and progress.finished_at is not None:
            return True
        if self.returned_book_checker is not None:
            return await self.returned_book_checker(user_id, book_id)
        return False

    async def rate(self, user_id: int, book_id: int, score: int, comment: str | None = None) -> Rating:
        if isinstance(score, bool) or not isinstance(score, int) or not MIN_SCORE <= score <= MAX_SCORE:
            raise ValueError(f"Оценка должна быть целым числом от {MIN_SCORE} до {MAX_SCORE}")
        book = await self.book_repo.get_by_id(book_id)
        if book is None or book.status == BookStatus.DRAFT:
            raise ValueError("Книга не найдена")
        if not await self._has_finished(user_id, book_id):
            raise ValueError(
                "Оценить книгу можно после дочитывания или возврата бумажного экземпляра"
            )
        comment = (comment or "").strip() or None
        async with self._transaction():
            rating = await self.rating_repo.create_or_update(user_id, book_id, score, comment)
        return rating

    async def delete_rating(self, user_id: int, book_id: int) -> None:
        async with self._transaction():
            await self.rating_repo.delete(user_id, book_id)

    async def get_user_rating(self, user_id: int, book_id: int) -> Rating | None:
        return await self.rating_repo.get_by_user_and_book(user_id, book_id)

    async def get_book_summary(self, book_id: int) -> RatingSummary:
        count, avg = await self.rating_repo.get_summary(book_id)
        return RatingSummary(count=count, average=round(float(avg), 2) if avg is not None else None)

    async def list_book_ratings(self, book_id: int, limit: int = 50, offset: int = 0) -> list[Rating]:
        return await self.rating_repo.list_by_book(book_id, max(1, min(limit, 200)), max(0, offset))