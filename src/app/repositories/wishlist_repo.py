from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models.user_book_relations import WishlistItem


class WishlistRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, user_id: int, book_id: int) -> WishlistItem | None:
        stmt = (
            pg_insert(WishlistItem)
            .values(user_id=user_id, book_id=book_id)
            .on_conflict_do_nothing(index_elements=[WishlistItem.user_id, WishlistItem.book_id])
            .returning(WishlistItem.id)
        )
        new_id = (await self.session.execute(stmt)).scalar_one_or_none()
        if new_id is None:
            return None
        return await self.session.get(WishlistItem, new_id)

    async def remove(self, user_id: int, book_id: int) -> None:
        await self.session.execute(
            delete(WishlistItem).where(
                WishlistItem.user_id == user_id,
                WishlistItem.book_id == book_id
            )
        )

    async def get_user_wishlist(self, user_id: int) -> list[WishlistItem]:
        result = await self.session.execute(
            select(WishlistItem)
            .options(selectinload(WishlistItem.book))
            .where(WishlistItem.user_id == user_id)
        )
        return list(result.scalars().all())