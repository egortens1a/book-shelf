from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models import FineReason, FineStatus


class FineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reservation_id: int
    amount: Decimal
    reason: FineReason
    status: FineStatus
    created_at: datetime
    paid_at: datetime | None = None


class FineListRead(BaseModel):
    """Штрафы читателя и сумма долга.

    unpaid_total отвечает на главный вопрос читателя - сколько он должен -
    и избавляет клиента от необходимости считать её самому.
    """

    items: list[FineRead]
    unpaid_total: Decimal
