from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.user_book_relations import WishlistItem


class WishlistRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, user_id: int, book_id: int) -> WishlistItem | None:
        """Добавляет книгу в вишлист; None, если она там уже есть."""
        exists = await self.session.scalar(
            select(WishlistItem.id).where(
                WishlistItem.user_id == user_id, WishlistItem.book_id == book_id
            )
        )
        if exists is not None:
            return None
        item = WishlistItem(user_id=user_id, book_id=book_id)
        self.session.add(item)
        await self.session.flush()
        await self.session.refresh(item)
        return item

    async def remove(self, user_id: int, book_id: int) -> None:
        await self.session.execute(
            delete(WishlistItem).where(
                WishlistItem.user_id == user_id, WishlistItem.book_id == book_id
            )
        )

    async def get_user_wishlist(self, user_id: int) -> list[WishlistItem]:
        result = await self.session.scalars(
            select(WishlistItem)
            .options(selectinload(WishlistItem.book))
            .where(WishlistItem.user_id == user_id)
        )
        return list(result.all())