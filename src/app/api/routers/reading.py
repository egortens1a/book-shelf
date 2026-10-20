"""Чтение электронных книг и прогресс. Весь блок - для читателя."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, get_reading_service
from app.schemas.reading import ProgressRead, ProgressUpdate, ReadingContentRead
from app.services.reading_service import ReadingService

ReadService = Annotated[ReadingService, Depends(get_reading_service)]

router = APIRouter(prefix="/books", tags=["reading"])


@router.get("/{book_id}/read", response_model=ReadingContentRead)
async def read_book(book_id: int, user: CurrentUser, reading: ReadService):
    """Текст книги и позиция, с которой читатель продолжит.

    Единственное место, где отдаётся text_content: в списках и карточках его
    нет. Отказы: книги нет или она черновик - 404; подписная книга без
    подписки - 403; у книги нет электронной версии или она в архиве и
    читатель её не начинал - 409.
    """
    text, position = await reading.open_for_reading(user.id, book_id)
    return ReadingContentRead(text=text, position=position)


@router.get("/{book_id}/progress", response_model=ProgressRead | None)
async def get_progress(book_id: int, user: CurrentUser, reading: ReadService):
    """Прогресс чтения. Книгу ещё не открывали - вернётся null, не ошибка."""
    progress = await reading.get_progress(user.id, book_id)
    return ProgressRead.model_validate(progress) if progress else None


@router.put("/{book_id}/progress", response_model=ProgressRead)
async def save_progress(
    book_id: int,
    data: ProgressUpdate,
    user: CurrentUser,
    reading: ReadService,
):
    """Сохраняет позицию чтения.

    PUT, а не POST: повторный запрос с той же позицией ничего не меняет.
    Позиция вне текста даёт 422. Отметка о прочтении ставится один раз,
    при достижении конца текста, и больше не трогается.
    """
    progress = await reading.save_position(user.id, book_id, data.position)
    return ProgressRead.model_validate(progress)
