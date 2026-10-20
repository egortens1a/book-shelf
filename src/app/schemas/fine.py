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
