from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Fine, FineReason, FineStatus, Reservation
from app.repositories import FineRepository
from app.services.base import BaseService
from app.core.errors import FineNotFound


class FineService(BaseService):
    """Начисление и оплата штрафов."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.fine_repo = FineRepository(session)
        self._settings = get_settings()

    def overdue_days(
        self, reservation: Reservation, at: datetime | None = None
    ) -> int:
        """Число полных суток просрочки к моменту `at`.

        Неполные сутки не считаются: по ТЗ пеня начисляется «за каждые
        полные сутки просрочки». Метод синхронный - в базу не ходит.
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
        async with self._transaction():
            return await self.fine_repo.create(
                reservation_id=reservation.id,
                amount=self._settings.fine_per_day * days,
                reason=FineReason.LATE_RETURN,
            )

    async def charge_lost(self, reservation: Reservation) -> Fine:
        """Начисляет фиксированный штраф за утерянный экземпляр."""
        async with self._transaction():
            return await self.fine_repo.create(
                reservation_id=reservation.id,
                amount=self._settings.fine_lost,
                reason=FineReason.LOST,
            )

    async def pay(self, fine_id: int) -> Fine:
        """Отмечает оплату штрафа. Делает библиотекарь.

        Повторная оплата не ошибка: операция идемпотентна.
        """
        async with self._transaction():
            fine = await self.fine_repo.get_for_update(fine_id)
            if fine is None:
                raise FineNotFound(f"Штраф {fine_id} не найден")
            if fine.status is FineStatus.PAID:
                return fine
            fine.status = FineStatus.PAID
            fine.paid_at = datetime.now(timezone.utc)
            await self.session.flush()
            return fine

    async def has_unpaid(self, user_id: int) -> bool:
        """Неоплаченный штраф закрывает читателю новые брони."""
        return await self.fine_repo.has_unpaid(user_id)

    async def list_for_user(self, user_id: int) -> list[Fine]:
        """Все штрафы читателя, включая оплаченные."""
        return await self.fine_repo.list_by_user(user_id)

    async def list_unpaid(self, user_id: int) -> list[Fine]:
        return await self.fine_repo.list_unpaid(user_id)
