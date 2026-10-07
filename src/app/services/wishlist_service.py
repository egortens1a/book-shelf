from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Book, BookStatus
from app.repositories import BookRepository, WishlistRepository
from app.services.base import BaseService


class WishlistService(BaseService):
    def __init__(self, session: AsyncSession):
        super().__init__(session)
        self.book_repo = BookRepository(session)
        self.wishlist_repo = WishlistRepository(session)

    async def add(self, user_id: int, book_id: int) -> bool:
        """True - книга добавлена, False - она уже была в списке"""
        book = await self.book_repo.get_by_id(book_id)
        if book is None or book.status != BookStatus.PUBLISHED:
            raise ValueError("Книга недоступна")
        async with self._transaction():
            item = await self.wishlist_repo.add(user_id, book_id)
        return item is not None

    async def remove(self, user_id: int, book_id: int) -> None:
        async with self._transaction():
            await self.wishlist_repo.remove(user_id, book_id)

    async def get_wishlist(self, user_id: int) -> list[Book]:
        items = await self.wishlist_repo.get_user_wishlist(user_id)
        return [item.book for item in items]