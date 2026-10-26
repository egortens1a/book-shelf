"""Подписка читателя. Идентификатор берётся из токена, не из пути."""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, get_subscription_service
from app.schemas.subscription import SubscriptionRead, SubscriptionStateRead
from app.services.subscription_service import SubscriptionService

router = APIRouter(prefix="/me", tags=["subscriptions"])

SubsService = Annotated[SubscriptionService, Depends(get_subscription_service)]


@router.post(
    "/subscription",
    response_model=SubscriptionRead,
    status_code=status.HTTP_201_CREATED,
)
async def subscribe(user: CurrentUser, subscriptions: SubsService):
    """Оформляет подписку, а если она уже действует - продление.

    Отдельного эндпоинта «продлить» нет намеренно: читатель нажимает ту же
    кнопку, а куда встанет период, решает сервис. Второе продление, когда
    одно уже в очереди, даёт 409.
    """
    subscription = await subscriptions.subscribe(user.id)
    return SubscriptionRead.model_validate(subscription)


@router.get("/subscription", response_model=SubscriptionStateRead)
async def current_subscription(user: CurrentUser, subscriptions: SubsService):
    """Действующий период и продление в очереди.

    Перед чтением вызывается sync_statuses: истёкшая подписка закрывается,
    наступившее продление открывается. Это запись внутри GET, но наблюдаемое
    состояние она не меняет - доступ всё равно определяется по датам, а не по
    статусу, так что ответ был бы тем же и без неё.
    """
    await subscriptions.sync_statuses(user.id)
    current = await subscriptions.get_effective(user.id)
    queued = await subscriptions.get_queued(user.id)
    return SubscriptionStateRead(
        current=SubscriptionRead.model_validate(current) if current else None,
        queued=SubscriptionRead.model_validate(queued) if queued else None,
        is_active=current is not None,
    )


@router.get("/subscriptions", response_model=list[SubscriptionRead])
async def subscription_history(user: CurrentUser, subscriptions: SubsService):
    """История подписок читателя, включая истёкшие."""
    items = await subscriptions.list_for_user(user.id)
    return [SubscriptionRead.model_validate(item) for item in items]
