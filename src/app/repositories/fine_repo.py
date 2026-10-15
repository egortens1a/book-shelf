from decimal import Decimal

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Fine, FineReason, FineStatus, Reservation


class FineRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self, reservation_id: int, amount: Decimal, reason: FineReason
    ) -> Fine:
        fine = Fine(
            reservation_id=reservation_id,
            amount=amount,
            reason=reason,
            status=FineStatus.UNPAID,
        )
        self.session.add(fine)
        await self.session.flush()
        await self.session.refresh(fine)
        return fine

    async def get_by_id(self, fine_id: int) -> Fine | None:
        return await self.session.get(Fine, fine_id)

    async def get_for_update(self, fine_id: int) -> Fine | None:
        """Штраф с блокировкой строки до конца транзакции."""
        return await self.session.get(Fine, fine_id, with_for_update=True)

    async def has_unpaid(self, user_id: int) -> bool:
        """Неоплаченный штраф закрывает читателю новые брони."""
        return bool(
            await self.session.scalar(
                select(
                    exists().where(
                        Fine.status == FineStatus.UNPAID,
                        Fine.reservation_id == Reservation.id,
                        Reservation.user_id == user_id,
                    )
                )
            )
        )

    async def list_unpaid(self, user_id: int) -> list[Fine]:
        result = await self.session.scalars(
            select(Fine)
            .join(Reservation, Reservation.id == Fine.reservation_id)
            .where(Reservation.user_id == user_id, Fine.status == FineStatus.UNPAID)
            .order_by(Fine.created_at)
        )
        return list(result.all())

    async def list_by_reservation(self, reservation_id: int) -> list[Fine]:
        result = await self.session.scalars(
            select(Fine)
            .where(Fine.reservation_id == reservation_id)
            .order_by(Fine.created_at)
        )
        return list(result.all())