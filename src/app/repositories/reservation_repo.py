from datetime import datetime

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BookCopy, Reservation, ReservationStatus

#: Бронь занимает экземпляр, пока находится в одном из этих состояний.
#: Тот же набор зашит в частичный индекс uq_reservations_copy_active.
ACTIVE_STATUSES = (ReservationStatus.CREATED, ReservationStatus.ISSUED)


class ReservationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self, user_id: int, copy_id: int, pickup_deadline: datetime
    ) -> Reservation:
        reservation = Reservation(
            user_id=user_id,
            copy_id=copy_id,
            status=ReservationStatus.CREATED,
            pickup_deadline=pickup_deadline,
        )
        self.session.add(reservation)
        await self.session.flush()
        await self.session.refresh(reservation)
        return reservation

    async def get_by_id(self, reservation_id: int) -> Reservation | None:
        return await self.session.get(Reservation, reservation_id)

    async def get_for_update(self, reservation_id: int) -> Reservation | None:
        """Бронь с блокировкой строки до конца транзакции."""
        return await self.session.get(
            Reservation, reservation_id, with_for_update=True
        )

    async def count_active(self, user_id: int) -> int:
        """Сколько броней и выдач у читателя на руках прямо сейчас."""
        result = await self.session.execute(
            select(func.count())
            .select_from(Reservation)
            .where(
                Reservation.user_id == user_id,
                Reservation.status.in_(ACTIVE_STATUSES),
            )
        )
        return result.scalar_one()

    async def has_overdue(self, user_id: int, now: datetime) -> bool:
        """Есть ли невозвращённая книга с истёкшим сроком чтения."""
        result = await self.session.execute(
            select(
                exists().where(
                    Reservation.user_id == user_id,
                    Reservation.status == ReservationStatus.ISSUED,
                    Reservation.due_date <= now,
                )
            )
        )
        return bool(result.scalar_one())

    async def holds_book(self, user_id: int, book_id: int) -> bool:
        """Закреплён ли за читателем экземпляр этой книги прямо сейчас."""
        result = await self.session.execute(
            select(
                exists().where(
                    Reservation.user_id == user_id,
                    Reservation.status.in_(ACTIVE_STATUSES),
                    Reservation.copy_id == BookCopy.id,
                    BookCopy.book_id == book_id,
                )
            )
        )
        return bool(result.scalar_one())

    async def has_returned(self, user_id: int, book_id: int) -> bool:
        """Брал ли читатель бумажный экземпляр книги и вернул ли его.

        Утерянная книга возвращённой не считается: такая бронь закрывается
        статусом LOST, которого в условии нет.
        """
        result = await self.session.execute(
            select(
                exists().where(
                    Reservation.user_id == user_id,
                    Reservation.status == ReservationStatus.RETURNED,
                    Reservation.copy_id == BookCopy.id,
                    BookCopy.book_id == book_id,
                )
            )
        )
        return bool(result.scalar_one())

    async def lock_stale_pickups(self, now: datetime) -> list[Reservation]:
        """Брони, которые не забрали в срок, с блокировкой строк.

        SKIP LOCKED нужен, чтобы параллельный вызов не ждал те же строки:
        пропущенные брони истекут при следующем обращении.
        """
        result = await self.session.execute(
            select(Reservation)
            .where(
                Reservation.status == ReservationStatus.CREATED,
                Reservation.pickup_deadline <= now,
            )
            .with_for_update(skip_locked=True)
        )
        return list(result.scalars().all())

    async def list_by_user(self, user_id: int) -> list[Reservation]:
        result = await self.session.execute(
            select(Reservation)
            .where(Reservation.user_id == user_id)
            .order_by(Reservation.created_at)
        )
        return list(result.scalars().all())
