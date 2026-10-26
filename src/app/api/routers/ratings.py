"""Оценки книг: поставить или изменить, удалить, посмотреть оценки книги."""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import get_current_user, get_rating_service, require_role
from app.models import RoleTypes, User
from app.schemas.rating import RatingIn, RatingRead
from app.services.rating_service import RatingService

router = APIRouter(prefix="/books", tags=["ratings"])

Ratings = Annotated[RatingService, Depends(get_rating_service)]
Reader = Annotated[User, Depends(require_role(RoleTypes.READER))]


@router.put("/{book_id}/rating", response_model=RatingRead)
async def rate_book(book_id: int, data: RatingIn, user: Reader, service: Ratings):
    """Создаёт оценку или меняет существующую. user_id берётся из токена."""
    return await service.rate(user.id, book_id, data.score, data.comment)


@router.delete("/{book_id}/rating", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rating(book_id: int, user: Reader, service: Ratings):
    await service.delete_rating(user.id, book_id)


@router.get(
    "/{book_id}/ratings",
    response_model=list[RatingRead],
    dependencies=[Depends(get_current_user)],
)
async def list_book_ratings(book_id: int, service: Ratings):
    return await service.list_book_ratings(book_id)