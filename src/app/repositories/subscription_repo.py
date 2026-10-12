from datetime import datetime
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Subscription, SubscriptionStatus


class SubscriptionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        user_id: int,
        price: Decimal,
        status: SubscriptionStatus,
        started_at: datetime,
        expires_at: datetime,
    ) -> Subscription:
        subscription = Subscription(
            user_id=user_id,
            price=price,
            status=status,
            started_at=started_at,
            expires_at=expires_at,
        )
        self.session.add(subscription)
        await self.session.flush()
        await self.session.refresh(subscription)
        return subscription

    async def get_effective(self, user_id: int, now: datetime) -> Subscription | None:
        """Оплаченный период, действующий в момент `now`.

        Отбор идёт по датам, а не по статусу: PENDING включён на случай,
        если ленивый перевод статусов ещё не отработал.
        """
        result = await self.session.execute(
            select(Subscription).where(
                Subscription.user_id == user_id,
                Subscription.status.in_(
                    [SubscriptionStatus.ACTIVE, SubscriptionStatus.PENDING]
                ),
                Subscription.started_at <= now,
                Subscription.expires_at > now,
            )
        )
        return result.scalar_one_or_none()

    async def get_queued(self, user_id: int, now: datetime) -> Subscription | None:
        """Оплаченное продление, которое ещё не вступило в силу."""
        result = await self.session.execute(
            select(Subscription).where(
                Subscription.user_id == user_id,
                Subscription.status == SubscriptionStatus.PENDING,
                Subscription.started_at > now,
            )
        )
        return result.scalar_one_or_none()

    async def expire_outdated(self, user_id: int, now: datetime) -> None:
        """Закрывает подписки, срок которых истёк."""
        await self.session.execute(
            update(Subscription)
            .where(
                Subscription.user_id == user_id,
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.expires_at <= now,
            )
            .values(status=SubscriptionStatus.EXPIRED)
        )

    async def activate_started(self, user_id: int, now: datetime) -> None:
        """Переводит в действующие продления, время которых наступило.

        Вызывать строго после expire_outdated: иначе на мгновение возникнут
        две записи со статусом ACTIVE и сработает uq_subscriptions_user_active.
        """
        await self.session.execute(
            update(Subscription)
            .where(
                Subscription.user_id == user_id,
                Subscription.status == SubscriptionStatus.PENDING,
                Subscription.started_at <= now,
            )
            .values(status=SubscriptionStatus.ACTIVE)
        )

    async def list_by_user(self, user_id: int) -> list[Subscription]:
        result = await self.session.execute(
            select(Subscription)
            .where(Subscription.user_id == user_id)
            .order_by(Subscription.started_at)
        )
        return list(result.scalars().all())
