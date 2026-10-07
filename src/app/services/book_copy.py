from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Book, BookCopy, CopyStatus
from app.services.errors import (
    BookNotFound,
    CopyNotAvailable,
    CopyNotFound,
    DuplicateInventoryNumber,
)


class BookCopyService:
    """Учёт бумажных экземпляров: постановка на учёт, списание, поиск свободных.

    Отметки утери здесь нет намеренно: она закрывает бронь и начисляет
    штраф, то есть касается не только экземпляра, и живёт в сервисе выдачи.

    Сервис не вызывает commit: транзакцией управляет вызывающий код.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, copy_id: int) -> BookCopy:
        copy = await self._session.get(BookCopy, copy_id)
        if copy is None:
            raise CopyNotFound(f"Экземпляр {copy_id} не найден")
        return copy

    async def register(self, book_id: int, inventory_number: str) -> BookCopy:
        """Ставит новый экземпляр на учёт.

        Книга может быть ещё черновиком: по ТЗ наличие экземпляра - одно
        из условий публикации, так что экземпляры заводятся до неё.
        """
        inventory_number = inventory_number.strip()
        if await self._session.get(Book, book_id) is None:
            raise BookNotFound(f"Книга {book_id} не найдена")

        taken = await self._session.scalar(
            select(BookCopy.id).where(BookCopy.inventory_number == inventory_number)
        )
        if taken is not None:
            raise DuplicateInventoryNumber(
                f"Инвентарный номер {inventory_number} уже занят"
            )

        copy = BookCopy(
            book_id=book_id,
            inventory_number=inventory_number,
            status=CopyStatus.AVAILABLE,
        )
        self._session.add(copy)
        await self._session.flush()
        return copy

    async def write_off(self, copy_id: int) -> BookCopy:
        """Списывает экземпляр: ветхий, утерянный или выбывший иначе.

        Занятый экземпляр списать нельзя - сначала его надо вернуть,
        иначе бронь осталась бы висеть на выбывшей книге.
        """
        copy = await self._session.get(BookCopy, copy_id, with_for_update=True)
        if copy is None:
            raise CopyNotFound(f"Экземпляр {copy_id} не найден")
        if copy.status not in (CopyStatus.AVAILABLE, CopyStatus.LOST):
            raise CopyNotAvailable(
                f"Экземпляр {copy.inventory_number} в статусе {copy.status.value}: "
                "списать можно только свободный или утерянный"
            )
        copy.status = CopyStatus.WRITTEN_OFF
        await self._session.flush()
        return copy

    async def count_available(self, book_id: int) -> int:
        """Сколько экземпляров книги сейчас свободно - для карточки книги."""
        count = await self._session.scalar(
            select(func.count())
            .select_from(BookCopy)
            .where(
                BookCopy.book_id == book_id,
                BookCopy.status == CopyStatus.AVAILABLE,
            )
        )
        return count or 0

    async def lock_free_copy(self, book_id: int) -> BookCopy | None:
        """Находит свободный экземпляр и блокирует его до конца транзакции.

        SKIP LOCKED пропускает экземпляры, которые прямо сейчас забирает
        другая транзакция, и берёт следующий свободный. Без него два
        одновременных бронирования встали бы в очередь на одну и ту же
        строку, и второй читатель ждал бы отказа, хотя на полке есть
        другие экземпляры этой же книги.
        """
        return await self._session.scalar(
            select(BookCopy)
            .where(
                BookCopy.book_id == book_id,
                BookCopy.status == CopyStatus.AVAILABLE,
            )
            .order_by(BookCopy.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
