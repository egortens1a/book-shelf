from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models import ReservationStatus
from app.schemas.fine import FineRead


class ReservationCreate(BaseModel):
    """Читатель бронирует книгу, а не конкретный экземпляр.

    Какой экземпляр закрепить, решает сервис: он берёт первый свободный
    с блокировкой строки.
    """

    book_id: int


class ReservationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    copy_id: int
    status: ReservationStatus
    created_at: datetime
    pickup_deadline: datetime
    issued_at: datetime | None = None
    due_date: datetime | None = None
    returned_at: datetime | None = None

    # На модели Reservation этих полей нет: книга достаётся через экземпляр,
    # а пеня до возврата нигде не хранится и считается на лету
    # (FineService.accrued_amount). Заполняет роутер.
    book_id: int | None = None
    book_title: str | None = None
    inventory_number: str | None = None
    accrued_fine: Decimal = Decimal("0.00")


class ReservationWithFine(BaseModel):
    """Ответ на приём возврата и на отметку утери.

    При возврате вовремя штрафа нет, поэтому поле необязательное.
    """

    reservation: ReservationRead
    fine: FineRead | None = None
