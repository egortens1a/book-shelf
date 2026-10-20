"""Зависимости FastAPI: аутентификация, роли и сборка сервисов.

Менять только через согласование: файл общий для обоих участников.
Пути импортов и имена конструкторов взяты из ТЗ (раздел 1.6),
сверьте их с реальным кодом.
"""

from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Forbidden, Unauthorized
from app.core.security import decode_token
from app.core.db import get_async_session
from app.models import RoleTypes, User, UserStatus
from app.repositories.user_repo import UserRepository
from app.services.book_copy_service import BookCopyService
from app.services.catalog_service import CatalogService
from app.services.directory_service import DirectoryService
from app.services.fine_service import FineService
from app.services.rating_service import RatingService
from app.services.reading_service import ReadingService
from app.services.reservation_service import ReservationService
from app.services.stats_service import StatsService
from app.services.subscription_service import SubscriptionService
from app.services.user_service import UserService
from app.services.wishlist_service import WishlistService

# auto_error=False: при отсутствии заголовка ошибку бросаем сами (Unauthorized),
# чтобы ответ шёл через общий обработчик в формате {"detail": ...}.
# tokenUrl должен совпадать с реальным путём логина (с учётом префикса роутера).
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login", auto_error=False)

SessionDep = Annotated[AsyncSession, Depends(get_async_session)]


# ---------- Аутентификация и роли ----------

async def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    session: SessionDep,
) -> User:
    """Пользователь из БД по токену. Читаем на каждом запросе."""
    if not token:
        raise Unauthorized("Not authenticated")

    payload = decode_token(token)  # бросает Unauthorized: подпись, срок, формат
    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        raise Unauthorized("Invalid token") from None

    user = await UserRepository(session).get_by_id(user_id)
    if user is None:
        raise Unauthorized("User not found")
    if user.status == UserStatus.BLOCKED:
        raise Forbidden("User is blocked")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(*roles: RoleTypes):
    """Фабрика зависимостей: пропускает только пользователей с одной из ролей.

    Роль определяется по БД (join User -> Role), а не по role_id из токена.
    """

    async def dependency(user: CurrentUser, session: SessionDep) -> User:
        role = await UserRepository(session).get_role_name(user.id)
        if role not in roles:
            raise Forbidden("Insufficient permissions")
        return user

    return dependency


# ---------- Сервисы ----------

def get_user_service(session: SessionDep) -> UserService:
    return UserService(session)


def get_catalog_service(session: SessionDep) -> CatalogService:
    return CatalogService(session)


def get_directory_service(session: SessionDep) -> DirectoryService:
    return DirectoryService(session)


def get_book_copy_service(session: SessionDep) -> BookCopyService:
    return BookCopyService(session)


def get_subscription_service(session: SessionDep) -> SubscriptionService:
    return SubscriptionService(session)


def get_reservation_service(session: SessionDep) -> ReservationService:
    return ReservationService(session)


def get_fine_service(session: SessionDep) -> FineService:
    return FineService(session)


def get_wishlist_service(session: SessionDep) -> WishlistService:
    return WishlistService(session)


def get_stats_service(session: SessionDep) -> StatsService:
    return StatsService(session)


def get_reading_service(
    session: SessionDep,
    subs: Annotated[SubscriptionService, Depends(get_subscription_service)],
) -> ReadingService:
    return ReadingService(session, subscription_checker=subs.has_active)


def get_rating_service(
    session: SessionDep,
    res: Annotated[ReservationService, Depends(get_reservation_service)],
) -> RatingService:
    return RatingService(session, returned_book_checker=res.has_returned)