"""Штрафы: читатель видит свои, библиотекарь отмечает оплату."""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, get_fine_service, require_role
from app.models import FineStatus, RoleTypes
from app.schemas.fine import FineListRead, FineRead
from app.services.fine_service import FineService

FinesService = Annotated[FineService, Depends(get_fine_service)]

reader_router = APIRouter(prefix="/me", tags=["fines"])
librarian_router = APIRouter(
    prefix="/librarian",
    tags=["fines"],
    dependencies=[Depends(require_role(RoleTypes.LIBRARIAN))],
)


@reader_router.get("/fines", response_model=FineListRead)
async def my_fines(user: CurrentUser, fines: FinesService):
    """История штрафов читателя и сумма неоплаченных.

    Сумма считается по уже выбранным записям, отдельный запрос не нужен.
    """
    items = await fines.list_for_user(user.id)
    unpaid_total = sum(
        (item.amount for item in items if item.status is FineStatus.UNPAID),
        Decimal("0.00"),
    )
    return FineListRead(
        items=[FineRead.model_validate(item) for item in items],
        unpaid_total=unpaid_total,
    )


@librarian_router.post("/fines/{fine_id}/pay", response_model=FineRead)
async def pay_fine(fine_id: int, fines: FinesService):
    """Отмечает оплату штрафа.

    Операция идемпотентна: повторный вызов возвращает ту же запись и не
    меняет дату оплаты, поэтому ошибки при двойном нажатии не будет.
    """
    fine = await fines.pay(fine_id)
    return FineRead.model_validate(fine)
