from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models import SubscriptionStatus


class SubscriptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: SubscriptionStatus
    price: Decimal
    started_at: datetime
    expires_at: datetime


class SubscriptionStateRead(BaseModel):
    """Состояние подписки читателя для GET /me/subscription.

    `current` - оплаченный период, действующий прямо сейчас; `queued` -
    продление, которое ещё не вступило в силу. Оба поля могут быть пустыми.
    `is_active` берётся из SubscriptionService.has_active, то есть считается
    по датам, а не по статусу записи.
    """

    current: SubscriptionRead | None = None
    queued: SubscriptionRead | None = None
    is_active: bool
