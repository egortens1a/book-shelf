from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Subscription, SubscriptionStatus, User
from app.services.errors import SubscriptionAlreadyQueued, UserNotFound


class SubscriptionService:
    """Оформление и продление подписки.

    Сервис не вызывает commit: транзакцией управляет вызывающий код -
    сейчас демонстрационный скрипт, в дальнейшем обработчик FastAPI.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._settings = get_settings()

    async def _lock_user(self, user_id: int) -> User:
        """Блокирует строку пользователя до конца транзакции.

        Так два одновременных оформления подписки одним читателем
        выстраиваются в очередь, а не дерутся за уникальный индекс.
        """
        user = await self._session.scalar(
            select(User).where(User.id == user_id).with_for_update()
        )
        if user is None:
            raise UserNotFound(f"Пользователь {user_id} не найден")
        return user

    async def sync_statuses(self, user_id: int) -> None:
        """Ленивый перевод статусов вместо планировщика.

        Порядок обязателен: сначала закрываем истёкшую, потом открываем
        отложенную. В обратном порядке на мгновение получилось бы две
        записи со статусом ACTIVE, и uq_subscriptions_user_active упал бы.
        """
        now = datetime.now(timezone.utc)
        await self._session.execute(
            update(Subscription)
            .where(
                Subscription.user_id == user_id,
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.expires_at <= now,
            )
            .values(status=SubscriptionStatus.EXPIRED)
        )
        await self._session.execute(
            update(Subscription)
            .where(
                Subscription.user_id == user_id,
                Subscription.status == SubscriptionStatus.PENDING,
                Subscription.started_at <= now,
            )
            .values(status=SubscriptionStatus.ACTIVE)
        )

    async def get_effective(self, user_id: int) -> Subscription | None:
        """Оплаченный период, действующий прямо сейчас.

        Определяется по датам, а не по статусу: если ленивый перевод ещё
        не отработал, читатель с оплаченным продлением всё равно получит
        доступ, а читатель с не начавшимся периодом - не получит.
        """
        now = datetime.now(timezone.utc)
        return await self._session.scalar(
            select(Subscription).where(
                Subscription.user_id == user_id,
                Subscription.status.in_(
                    [SubscriptionStatus.ACTIVE, SubscriptionStatus.PENDING]
                ),
                Subscription.started_at <= now,
                Subscription.expires_at > now,
            )
        )

    async def has_active(self, user_id: int) -> bool:
        """Используется бронированием: без подписки бронь не создаётся."""
        return (await self.get_effective(user_id)) is not None

    async def get_queued(self, user_id: int) -> Subscription | None:
        """Оплаченное продление, которое ещё не вступило в силу."""
        now = datetime.now(timezone.utc)
        return await self._session.scalar(
            select(Subscription).where(
                Subscription.user_id == user_id,
                Subscription.status == SubscriptionStatus.PENDING,
                Subscription.started_at > now,
            )
        )

    async def subscribe(self, user_id: int) -> Subscription:
        """Оформляет подписку, а если она уже действует - продление.

        Отдельного метода для продления нет намеренно: читатель нажимает
        одну и ту же кнопку, а куда встанет период, решает сервис.
        """
        await self._lock_user(user_id)
        await self.sync_statuses(user_id)

        if await self.get_queued(user_id) is not None:
            raise SubscriptionAlreadyQueued(
                "Продление уже оплачено: в очереди не может быть больше одной подписки"
            )

        current = await self.get_effective(user_id)
        if current is None:
            started_at = datetime.now(timezone.utc)
            status = SubscriptionStatus.ACTIVE
        else:
            started_at = current.expires_at
            status = SubscriptionStatus.PENDING

        subscription = Subscription(
            user_id=user_id,
            price=Decimal(self._settings.subscription_price),
            status=status,
            started_at=started_at,
            expires_at=started_at + timedelta(days=self._settings.subscription_days),
        )
        self._session.add(subscription)
        await self._session.flush()
        return subscription
