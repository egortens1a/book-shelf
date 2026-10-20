from datetime import datetime

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import BookCopy, Reservation, ReservationStatus

#: Бронь занимает экземпляр, пока находится в одном из этих состояний.
#: Тот же набор зашит в частичный индекс uq_reservations_copy_active.
ACTIVE_STATUSES = (ReservationStatus.CREATED, ReservationStatus.ISSUED)

#: Для карточки брони нужны инвентарный номер и название книги. Связи
#: объявлены с lazy="raise", поэтому без этих опций DTO не собрать.
_CARD_OPTIONS = (selectinload(Reservation.copy).selectinload(BookCopy.book),)


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
        return await self.session.get(Reservation, reservation_id, with_for_update=True)

    async def _exists_where(self, *conditions) -> bool:
        """EXISTS по условиям; в запросе нет ничего, кроме самих условий."""
        return bool(await self.session.scalar(select(exists().where(*conditions))))

    async def count_active(self, user_id: int) -> int:
        """Сколько броней и выдач у читателя на руках прямо сейчас.

        COUNT всегда возвращает строку, поэтому None здесь невозможен;
        `or 0` стоит лишь ради честной аннотации типа.
        """
        return await self.session.scalar(
            select(func.count(Reservation.id)).where(
                Reservation.user_id == user_id,
                Reservation.status.in_(ACTIVE_STATUSES),
            )
        ) or 0

    async def has_overdue(self, user_id: int, now: datetime) -> bool:
        """Есть ли невозвращённая книга с истёкшим сроком чтения."""
        return await self._exists_where(
            Reservation.user_id == user_id,
            Reservation.status == ReservationStatus.ISSUED,
            Reservation.due_date <= now,
        )

    async def holds_book(self, user_id: int, book_id: int) -> bool:
        """Закреплён ли за читателем экземпляр этой книги прямо сейчас."""
        return await self._exists_where(
            Reservation.user_id == user_id,
            Reservation.status.in_(ACTIVE_STATUSES),
            Reservation.copy_id == BookCopy.id,
            BookCopy.book_id == book_id,
        )

    async def has_returned(self, user_id: int, book_id: int) -> bool:
        """Брал ли читатель бумажный экземпляр книги и вернул ли его.

        Утерянная книга возвращённой не считается: такая бронь закрывается
        статусом LOST, которого в условии нет.
        """
        return await self._exists_where(
            Reservation.user_id == user_id,
            Reservation.status == ReservationStatus.RETURNED,
            Reservation.copy_id == BookCopy.id,
            BookCopy.book_id == book_id,
        )

    async def lock_stale_pickups(self, now: datetime) -> list[Reservation]:
        """Брони, которые не забрали в срок, с блокировкой строк.

        SKIP LOCKED нужен, чтобы параллельный вызов не ждал те же строки:
        пропущенные брони истекут при следующем обращении.
        """
        result = await self.session.scalars(
            select(Reservation)
            .where(
                Reservation.status == ReservationStatus.CREATED,
                Reservation.pickup_deadline <= now,
            )
            .with_for_update(skip_locked=True)
        )
        return list(result.all())

    async def list_by_user(self, user_id: int) -> list[Reservation]:
        """История броней читателя, от новых к старым."""
        result = await self.session.scalars(
            select(Reservation)
            .options(*_CARD_OPTIONS)
            .where(Reservation.user_id == user_id)
            .order_by(Reservation.created_at.desc(), Reservation.id.desc())
        )
        return list(result.all())

    async def list_filtered(
        self,
        status: ReservationStatus | None = None,
        user_id: int | None = None,
        inventory_number: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Reservation]:
        """Список броней для библиотекаря.

        Фильтр по инвентарному номеру требует соединения с экземпляром,
        поэтому join добавляется только когда он действительно нужен.
        """
        query = select(Reservation).options(*_CARD_OPTIONS)
        if status is not None:
            query = query.where(Reservation.status == status)
        if user_id is not None:
            query = query.where(Reservation.user_id == user_id)
        if inventory_number:
            query = query.join(BookCopy, BookCopy.id == Reservation.copy_id).where(
                BookCopy.inventory_number == inventory_number.strip()
            )
        query = (
            query.order_by(Reservation.created_at.desc(), Reservation.id.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.scalars(query)
        return list(result.all())