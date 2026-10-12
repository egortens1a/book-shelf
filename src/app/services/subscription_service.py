from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Subscription, SubscriptionStatus
from app.repositories import SubscriptionRepository
from app.services.base import BaseService
from app.services.errors import SubscriptionAlreadyQueued, UserNotFound


class SubscriptionService(BaseService):
    """Оформление и продление подписки.

    Сервис не фиксирует транзакцию: _transaction() открывает точку
    сохранения, а commit остаётся за вызывающим кодом.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.subscription_repo = SubscriptionRepository(session)
        self._settings = get_settings()

    async def sync_statuses(self, user_id: int) -> None:
        """Ленивый перевод статусов вместо планировщика.

        Порядок обязателен: сначала закрываем истёкшую, потом открываем
        отложенную. В обратном порядке на мгновение получилось бы две
        записи со статусом ACTIVE, и uq_subscriptions_user_active упал бы.
        """
        now = datetime.now(timezone.utc)
        async with self._transaction():
            await self.subscription_repo.expire_outdated(user_id, now)
            await self.subscription_repo.activate_started(user_id, now)

    async def get_effective(self, user_id: int) -> Subscription | None:
        """Оплаченный период, действующий прямо сейчас.

        Определяется по датам, а не по статусу: если ленивый перевод ещё
        не отработал, читатель с оплаченным продлением всё равно получит
        доступ, а читатель с не начавшимся периодом - не получит.
        """
        return await self.subscription_repo.get_effective(
            user_id, datetime.now(timezone.utc)
        )

    async def has_active(self, user_id: int) -> bool:
        """Используется бронированием: без подписки бронь не создаётся.

        Подходит под протокол SubscriptionChecker блока А.
        """
        return (await self.get_effective(user_id)) is not None

    async def get_queued(self, user_id: int) -> Subscription | None:
        """Оплаченное продление, которое ещё не вступило в силу."""
        return await self.subscription_repo.get_queued(
            user_id, datetime.now(timezone.utc)
        )

    async def subscribe(self, user_id: int) -> Subscription:
        """Оформляет подписку, а если она уже действует - продление.

        Отдельного метода для продления нет намеренно: читатель нажимает
        одну и ту же кнопку, а куда встанет период, решает сервис.
        """
        async with self._transaction():
            if await self.user_repo.get_for_update(user_id) is None:
                raise UserNotFound(f"Пользователь {user_id} не найден")

            now = datetime.now(timezone.utc)
            await self.subscription_repo.expire_outdated(user_id, now)
            await self.subscription_repo.activate_started(user_id, now)

            if await self.subscription_repo.get_queued(user_id, now) is not None:
                raise SubscriptionAlreadyQueued(
                    "Продление уже оплачено: в очереди не может быть больше одной подписки"
                )

            current = await self.subscription_repo.get_effective(user_id, now)
            if current is None:
                started_at = now
                status = SubscriptionStatus.ACTIVE
            else:
                started_at = current.expires_at
                status = SubscriptionStatus.PENDING

            return await self.subscription_repo.create(
                user_id=user_id,
                price=self._settings.subscription_price,
                status=status,
                started_at=started_at,
                expires_at=started_at
                + timedelta(days=self._settings.subscription_days),
            )

    async def list_for_user(self, user_id: int) -> list[Subscription]:
        return await self.subscription_repo.list_by_user(user_id)
