"""Учёт бумажных экземпляров. Весь блок доступен только библиотекарю."""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import get_book_copy_service, require_role
from app.models import RoleTypes
from app.schemas.book_copy import BookCopyCreate, BookCopyRead
from app.services.book_copy_service import BookCopyService

# Проверка роли висит на всём роутере: отдельных прав у этих эндпоинтов нет.
router = APIRouter(
    tags=["copies"],
    dependencies=[Depends(require_role(RoleTypes.LIBRARIAN))],
)

CopyService = Annotated[BookCopyService, Depends(get_book_copy_service)]


@router.post(
    "/books/{book_id}/copies",
    response_model=BookCopyRead,
    status_code=status.HTTP_201_CREATED,
)
async def register_copy(book_id: int, data: BookCopyCreate, copies: CopyService):
    """Ставит экземпляр на учёт.

    Книга может быть ещё черновиком: наличие экземпляра - одно из условий
    публикации, так что экземпляры заводят до неё.
    """
    copy = await copies.register(book_id, data.inventory_number)
    return BookCopyRead.model_validate(copy)


@router.get("/books/{book_id}/copies", response_model=list[BookCopyRead])
async def list_copies(book_id: int, copies: CopyService):
    items = await copies.list_for_book(book_id)
    return [BookCopyRead.model_validate(item) for item in items]


@router.post("/copies/{copy_id}/write-off", response_model=BookCopyRead)
async def write_off_copy(copy_id: int, copies: CopyService):
    """Списывает экземпляр.

    Не DELETE: строка остаётся в базе, меняется только статус. На экземпляр
    ссылается история броней, физически удалить его нельзя.
    """
    copy = await copies.write_off(copy_id)
    return BookCopyRead.model_validate(copy)
