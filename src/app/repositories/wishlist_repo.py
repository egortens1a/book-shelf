from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Book
from app.models.user_book_relations import WishlistItem


class WishlistRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, user_id: int, book_id: int) -> WishlistItem | None:
        """Добавляет книгу в вишлист; None, если она там уже есть."""
        # INSERT ... ON CONFLICT DO NOTHING: вставка и разрешение конфликта
        # одним запросом. Проверка перед вставкой оставляла окно, в которое
        # при двойном клике проскакивал второй запрос и ловил IntegrityError.
        new_id = await self.session.scalar(
            pg_insert(WishlistItem)
            .values(user_id=user_id, book_id=book_id)
            .on_conflict_do_nothing(
                index_elements=[WishlistItem.user_id, WishlistItem.book_id]
            )
            .returning(WishlistItem.id)
        )
        if new_id is None:
            # RETURNING пуст - значит вставки не было, книга уже в списке.
            return None
        return await self.session.get(WishlistItem, new_id)

    async def remove(self, user_id: int, book_id: int) -> None:
        await self.session.execute(
            delete(WishlistItem).where(
                WishlistItem.user_id == user_id, WishlistItem.book_id == book_id
            )
        )

    async def get_user_wishlist(self, user_id: int) -> list[WishlistItem]:
        """Список «хочу прочитать» с книгами, авторами и жанрами.

        Авторы и жанры нужны в BookRead внутри ответа, а связи объявлены
        ленивыми - без явной догрузки сериализация упадёт.
        """
        result = await self.session.scalars(
            select(WishlistItem)
            .options(
                selectinload(WishlistItem.book).selectinload(Book.authors),
                selectinload(WishlistItem.book).selectinload(Book.genres),
            )
            .where(WishlistItem.user_id == user_id)
            .order_by(WishlistItem.created_at.desc(), WishlistItem.id.desc())
        )
        return list(result.all())