from collections.abc import Sequence
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Fine, FineReason, FineStatus, Reservation
from app.services.errors import FineNotFound


class FineService:
    """Начисление и оплата штрафов.

    Сервис не вызывает commit: транзакцией управляет вызывающий код.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._settings = get_settings()

    def overdue_days(
        self, reservation: Reservation, at: datetime | None = None
    ) -> int:
        """Число полных суток просрочки к моменту `at`.

        Неполные сутки не считаются: по ТЗ пеня начисляется «за каждые
        полные сутки просрочки».
        """
        if reservation.due_date is None:
            return 0
        moment = at or datetime.now(timezone.utc)
        days = (moment - reservation.due_date).days
        return days if days > 0 else 0

    def accrued_amount(
        self, reservation: Reservation, at: datetime | None = None
    ) -> Decimal:
        """Расчётная пеня по невозвращённой книге.

        По ТЗ до возврата размер пени в базе не хранится, а показывается
        расчётно - поэтому метод ничего не пишет и ничего не создаёт.
        """
        return self._settings.fine_per_day * self.overdue_days(reservation, at)

    async def charge_late_return(self, reservation: Reservation) -> Fine | None:
        """Начисляет пеню в момент приёма возврата. Вернули вовремя - None."""
        days = self.overdue_days(reservation, reservation.returned_at)
        if days == 0:
            return None
        fine = Fine(
            reservation_id=reservation.id,
            amount=self._settings.fine_per_day * days,
            reason=FineReason.LATE_RETURN,
            status=FineStatus.UNPAID,
        )
        self._session.add(fine)
        await self._session.flush()
        return fine

    async def charge_lost(self, reservation: Reservation) -> Fine:
        """Начисляет фиксированный штраф за утерянный экземпляр."""
        fine = Fine(
            reservation_id=reservation.id,
            amount=self._settings.fine_lost,
            reason=FineReason.LOST,
            status=FineStatus.UNPAID,
        )
        self._session.add(fine)
        await self._session.flush()
        return fine

    async def pay(self, fine_id: int) -> Fine:
        """Отмечает оплату штрафа. Делает библиотекарь."""
        fine = await self._session.get(Fine, fine_id, with_for_update=True)
        if fine is None:
            raise FineNotFound(f"Штраф {fine_id} не найден")
        if fine.status is FineStatus.PAID:
            return fine
        fine.status = FineStatus.PAID
        fine.paid_at = datetime.now(timezone.utc)
        await self._session.flush()
        return fine

    async def has_unpaid(self, user_id: int) -> bool:
        """Неоплаченный штраф закрывает читателю новые брони."""
        found = await self._session.scalar(
            select(
                exists().where(
                    Fine.status == FineStatus.UNPAID,
                    Fine.reservation_id == Reservation.id,
                    Reservation.user_id == user_id,
                )
            )
        )
        return bool(found)

    async def list_unpaid(self, user_id: int) -> Sequence[Fine]:
        return (
            await self._session.scalars(
                select(Fine)
                .join(Reservation, Reservation.id == Fine.reservation_id)
                .where(
                    Reservation.user_id == user_id,
                    Fine.status == FineStatus.UNPAID,
                )
                .order_by(Fine.created_at)
            )
        ).all()
