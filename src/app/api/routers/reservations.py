"""Бронирование бумажных экземпляров.

Два роутера: читательский под /me и библиотекарский под /librarian. Читатель
работает только со своими бронями, его идентификатор берётся из токена.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import (
    CurrentUser,
    get_fine_service,
    get_reservation_service,
    require_role,
)
from app.models import Reservation, ReservationStatus, RoleTypes
from app.schemas.fine import FineRead
from app.schemas.reservation import (
    ReservationCreate,
    ReservationRead,
    ReservationWithFine,
)
from app.services.fine_service import FineService
from app.services.reservation_service import ReservationService

ResService = Annotated[ReservationService, Depends(get_reservation_service)]
FinesService = Annotated[FineService, Depends(get_fine_service)]

reader_router = APIRouter(prefix="/me", tags=["reservations"])
librarian_router = APIRouter(
    prefix="/librarian",
    tags=["reservations"],
    dependencies=[Depends(require_role(RoleTypes.LIBRARIAN))],
)


def _to_read(reservation: Reservation, fines: FineService) -> ReservationRead:
    """Собирает DTO брони.

    Три поля на модели отсутствуют: книга достаётся через экземпляр, а пеня
    по ТЗ нигде не хранится и считается на лету. Поэтому схема заполняется
    явно, а не через model_validate.
    """
    copy = reservation.copy
    return ReservationRead(
        id=reservation.id,
        copy_id=reservation.copy_id,
        status=reservation.status,
        created_at=reservation.created_at,
        pickup_deadline=reservation.pickup_deadline,
        issued_at=reservation.issued_at,
        due_date=reservation.due_date,
        returned_at=reservation.returned_at,
        book_id=copy.book_id,
        book_title=copy.book.title,
        inventory_number=copy.inventory_number,
        accrued_fine=fines.accrued_amount(reservation),
    )


# ---------- читатель ----------


@reader_router.post(
    "/reservations",
    response_model=ReservationRead,
    status_code=status.HTTP_201_CREATED,
)
async def reserve(
    data: ReservationCreate,
    user: CurrentUser,
    reservations: ResService,
    fines: FinesService,
):
    """Бронирует свободный экземпляр книги.

    Читатель выбирает книгу, а какой экземпляр закрепить, решает сервис.
    Отказы: нет подписки и есть долги - 403, лимит, повтор и отсутствие
    свободных экземпляров - 409.
    """
    reservation = await reservations.reserve(user.id, data.book_id)
    return _to_read(await reservations.get_card(reservation.id), fines)


@reader_router.get("/reservations", response_model=list[ReservationRead])
async def my_reservations(user: CurrentUser, reservations: ResService, fines: FinesService):
    """История броней читателя, от новых к старым."""
    items = await reservations.list_for_user(user.id)
    return [_to_read(item, fines) for item in items]


@reader_router.post("/reservations/{reservation_id}/cancel", response_model=ReservationRead)
async def cancel_reservation(
    reservation_id: int,
    user: CurrentUser,
    reservations: ResService,
    fines: FinesService,
):
    """Отказ от брони до получения книги.

    Чужая бронь отдаётся как ненайденная: иначе перебором по id можно
    выяснить, какие брони существуют.
    """
    reservation = await reservations.cancel(reservation_id, user.id)
    return _to_read(await reservations.get_card(reservation.id), fines)


# ---------- библиотекарь ----------


@librarian_router.get("/reservations", response_model=list[ReservationRead])
async def list_reservations(
    reservations: ResService,
    fines: FinesService,
    status_filter: Annotated[ReservationStatus | None, Query(alias="status")] = None,
    user_id: Annotated[int | None, Query()] = None,
    inventory_number: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """Брони с фильтрами по статусу, читателю и инвентарному номеру."""
    items = await reservations.list_filtered(
        status=status_filter,
        user_id=user_id,
        inventory_number=inventory_number,
        limit=limit,
        offset=offset,
    )
    return [_to_read(item, fines) for item in items]


@librarian_router.post("/reservations/{reservation_id}/issue", response_model=ReservationRead)
async def issue(reservation_id: int, reservations: ResService, fines: FinesService):
    """Выдаёт забронированный экземпляр на руки.

    Если срок получения истёк, бронь закрывается, экземпляр возвращается
    в свободные, и клиент получает 409.
    """
    reservation = await reservations.issue(reservation_id)
    return _to_read(await reservations.get_card(reservation.id), fines)


@librarian_router.post(
    "/reservations/{reservation_id}/return", response_model=ReservationWithFine
)
async def return_book(reservation_id: int, reservations: ResService, fines: FinesService):
    """Принимает книгу. При просрочке начисляется пеня, иначе fine равен null."""
    reservation, fine = await reservations.return_book(reservation_id)
    return ReservationWithFine(
        reservation=_to_read(await reservations.get_card(reservation.id), fines),
        fine=FineRead.model_validate(fine) if fine else None,
    )


@librarian_router.post(
    "/reservations/{reservation_id}/lost", response_model=ReservationWithFine
)
async def mark_lost(reservation_id: int, reservations: ResService, fines: FinesService):
    """Фиксирует утерю выданного экземпляра. Штраф фиксированный."""
    reservation, fine = await reservations.mark_lost(reservation_id)
    return ReservationWithFine(
        reservation=_to_read(await reservations.get_card(reservation.id), fines),
        fine=FineRead.model_validate(fine),
    )
