"""Список «хочу прочитать»: читатель ведёт свою очередь ожидания."""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, get_wishlist_service
from app.schemas.catalog import BookRead
from app.services.wishlist_service import WishlistService

Wishlist = Annotated[WishlistService, Depends(get_wishlist_service)]

router = APIRouter(prefix="/me", tags=["wishlist"])


@router.get("/wishlist", response_model=list[BookRead])
async def my_wishlist(user: CurrentUser, wishlist: Wishlist):
    """Книги из списка, недавно добавленные сверху.

    Авторы и жанры догружает репозиторий: связи ленивые, и без этого
    сериализация BookRead упала бы.
    """
    return await wishlist.get_wishlist(user.id)


@router.put("/wishlist/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
async def add_to_wishlist(book_id: int, user: CurrentUser, wishlist: Wishlist) -> None:
    """Добавляет книгу в список.

    PUT, а не POST: операция идемпотентна. Повторное добавление не ошибка
    и список не меняет - в репозитории стоит ON CONFLICT DO NOTHING.
    Неопубликованная книга даёт 404, как и несуществующая.
    """
    await wishlist.add(user.id, book_id)


@router.delete("/wishlist/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_from_wishlist(
    book_id: int, user: CurrentUser, wishlist: Wishlist
) -> None:
    """Убирает книгу из списка. Удаление отсутствующей книги не ошибка."""
    await wishlist.remove(user.id, book_id)
