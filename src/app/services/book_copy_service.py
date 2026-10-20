from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BookCopy, CopyStatus
from app.repositories import BookCopyRepository, BookRepository
from app.services.base import BaseService
from app.core.errors import (
    BookNotFound,
    CopyNotAvailable,
    CopyNotFound,
    DuplicateInventoryNumber,
)


class BookCopyService(BaseService):
    """Учёт бумажных экземпляров: постановка на учёт, списание, поиск свободных.

    Отметки утери здесь нет намеренно: она закрывает бронь и начисляет
    штраф, то есть касается не только экземпляра, и живёт в сервисе выдачи.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.copy_repo = BookCopyRepository(session)
        self.book_repo = BookRepository(session)

    async def get(self, copy_id: int) -> BookCopy:
        copy = await self.copy_repo.get_by_id(copy_id)
        if copy is None:
            raise CopyNotFound(f"Экземпляр {copy_id} не найден")
        return copy

    async def register(self, book_id: int, inventory_number: str) -> BookCopy:
        """Ставит новый экземпляр на учёт.

        Книга может быть ещё черновиком: по ТЗ наличие экземпляра - одно
        из условий публикации, так что экземпляры заводятся до неё.
        """
        inventory_number = inventory_number.strip()
        if await self.book_repo.get_by_id(book_id) is None:
            raise BookNotFound(f"Книга {book_id} не найдена")

        taken_message = f"Инвентарный номер {inventory_number} уже занят"
        try:
            async with self._transaction():
                # Проверка даёт понятный отказ в обычном случае, но между ней
                # и вставкой другой библиотекарь может занять тот же номер.
                # Тогда сработает uq_book_copies_inventory_number, и ошибку
                # целостности надо перевести в ту же доменную ошибку.
                if await self.copy_repo.inventory_number_taken(inventory_number):
                    raise DuplicateInventoryNumber(taken_message)
                return await self.copy_repo.create(book_id, inventory_number)
        except IntegrityError as exc:
            raise DuplicateInventoryNumber(taken_message) from exc

    async def write_off(self, copy_id: int) -> BookCopy:
        """Списывает экземпляр: ветхий, утерянный или выбывший иначе.

        Занятый экземпляр списать нельзя - сначала его надо вернуть,
        иначе бронь осталась бы висеть на выбывшей книге.
        """
        async with self._transaction():
            copy = await self.copy_repo.get_for_update(copy_id)
            if copy is None:
                raise CopyNotFound(f"Экземпляр {copy_id} не найден")
            if copy.status not in (CopyStatus.AVAILABLE, CopyStatus.LOST):
                raise CopyNotAvailable(
                    f"Экземпляр {copy.inventory_number} в статусе {copy.status.value}: "
                    "списать можно только свободный или утерянный"
                )
            copy.status = CopyStatus.WRITTEN_OFF
            await self.session.flush()
            return copy

    async def count_available(self, book_id: int) -> int|None:
        """Сколько экземпляров книги сейчас свободно - для карточки книги."""
        return await self.copy_repo.count_available(book_id)

    async def list_for_book(self, book_id: int) -> list[BookCopy]:
        return await self.copy_repo.list_by_book(book_id)
