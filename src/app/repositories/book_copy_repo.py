from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BookCopy, CopyStatus


class BookCopyRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, book_id: int, inventory_number: str) -> BookCopy:
        copy = BookCopy(
            book_id=book_id,
            inventory_number=inventory_number,
            status=CopyStatus.AVAILABLE,
        )
        self.session.add(copy)
        await self.session.flush()
        await self.session.refresh(copy)
        return copy

    async def get_by_id(self, copy_id: int) -> BookCopy | None:
        return await self.session.get(BookCopy, copy_id)

    async def get_for_update(self, copy_id: int) -> BookCopy | None:
        """Экземпляр с блокировкой строки до конца транзакции."""
        return await self.session.get(BookCopy, copy_id, with_for_update=True)

    async def inventory_number_taken(self, inventory_number: str) -> bool:
        found = await self.session.scalar(
            select(BookCopy.id).where(BookCopy.inventory_number == inventory_number)
        )
        return found is not None

    async def count_available(self, book_id: int) -> int | None:
        return await self.session.scalar(
            select(func.count(BookCopy.id)).where(
                BookCopy.book_id == book_id,
                BookCopy.status == CopyStatus.AVAILABLE,
            )
        )

    async def lock_free(self, book_id: int) -> BookCopy | None:
        """Свободный экземпляр книги с блокировкой строки.

        SKIP LOCKED пропускает экземпляры, которые прямо сейчас забирает
        другая транзакция, и берёт следующий свободный. Без него второй
        читатель ждал бы ту же строку, хотя рядом есть другие экземпляры.
        """
        return await self.session.scalar(
            select(BookCopy)
            .where(
                BookCopy.book_id == book_id,
                BookCopy.status == CopyStatus.AVAILABLE,
            )
            .order_by(BookCopy.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )

    async def list_by_book(self, book_id: int) -> list[BookCopy]:
        result = await self.session.scalars(
            select(BookCopy)
            .where(BookCopy.book_id == book_id)
            .order_by(BookCopy.inventory_number)
        )
        return list(result.all())