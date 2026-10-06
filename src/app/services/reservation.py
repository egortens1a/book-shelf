from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import (
    Book,
    BookCopy,
    BookStatus,
    CopyStatus,
    Fine,
    Reservation,
    ReservationStatus,
)
from app.services.book_copy import BookCopyService
from app.services.errors import (
    AlreadyReserved,
    BookNotFound,
    BookNotPublished,
    HasOverdueLoan,
    HasUnpaidFine,
    InvalidReservationState,
    NoActiveSubscription,
    NoCopyAvailable,
    PickupExpired,
    ReservationNotFound,
    TooManyReservations,
)
from app.services.fine import FineService
from app.services.subscription import SubscriptionService

#: Бронь занимает экземпляр, пока находится в одном из этих состояний.
#: Тот же набор зашит в частичный индекс uq_reservations_copy_active.
ACTIVE_STATUSES = (ReservationStatus.CREATED, ReservationStatus.ISSUED)


class ReservationService:
    """Бронирование бумажных экземпляров, выдача, возврат и утеря.

    Сервис не вызывает commit: транзакцией управляет вызывающий код.
    Это важно именно здесь - бронирование меняет и бронь, и экземпляр,
    и обе записи должны уехать в базу одной транзакцией.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._settings = get_settings()
        self._subscriptions = SubscriptionService(session)
        self._copies = BookCopyService(session)
        self._fines = FineService(session)

    # ------------------------------------------------------------------
    # вспомогательные запросы
    # ------------------------------------------------------------------

    async def _lock(self, reservation_id: int) -> Reservation:
        reservation = await self._session.get(
            Reservation, reservation_id, with_for_update=True
        )
        if reservation is None:
            raise ReservationNotFound(f"Бронь {reservation_id} не найдена")
        return reservation

    async def _release_copy(
        self, reservation: Reservation, status: ReservationStatus
    ) -> None:
        """Закрывает бронь и возвращает экземпляр в свободные."""
        reservation.status = status
        copy = await self._session.get(
            BookCopy, reservation.copy_id, with_for_update=True
        )
        if copy is not None and copy.status is CopyStatus.RESERVED:
            copy.status = CopyStatus.AVAILABLE
        await self._session.flush()

    async def active_count(self, user_id: int) -> int:
        """Сколько броней и выдач у читателя на руках прямо сейчас."""
        count = await self._session.scalar(
            select(func.count())
            .select_from(Reservation)
            .where(
                Reservation.user_id == user_id,
                Reservation.status.in_(ACTIVE_STATUSES),
            )
        )
        return count or 0

    async def has_overdue(self, user_id: int) -> bool:
        """Есть ли невозвращённая книга с истёкшим сроком чтения."""
        now = datetime.now(timezone.utc)
        found = await self._session.scalar(
            select(
                exists().where(
                    Reservation.user_id == user_id,
                    Reservation.status == ReservationStatus.ISSUED,
                    Reservation.due_date <= now,
                )
            )
        )
        return bool(found)

    async def has_returned(self, user_id: int, book_id: int) -> bool:
        """True, если читатель брал бумажный экземпляр книги и вернул его.

        Нужен блоку А: по ТЗ оценку можно поставить после возврата
        бумажного экземпляра. Утерянная книга возвращённой не считается -
        такая бронь закрывается статусом LOST.
        """
        found = await self._session.scalar(
            select(
                exists().where(
                    Reservation.user_id == user_id,
                    Reservation.status == ReservationStatus.RETURNED,
                    Reservation.copy_id == BookCopy.id,
                    BookCopy.book_id == book_id,
                )
            )
        )
        return bool(found)

    async def _holds_book(self, user_id: int, book_id: int) -> bool:
        found = await self._session.scalar(
            select(
                exists().where(
                    Reservation.user_id == user_id,
                    Reservation.status.in_(ACTIVE_STATUSES),
                    Reservation.copy_id == BookCopy.id,
                    BookCopy.book_id == book_id,
                )
            )
        )
        return bool(found)

    # ------------------------------------------------------------------
    # ленивое истечение
    # ------------------------------------------------------------------

    async def expire_stale_pickups(self) -> int:
        """Закрывает брони, которые не забрали в срок, и освобождает экземпляры.

        Планировщика в проекте нет: вместо него истечение выполняется при
        обращении к бронированию. SKIP LOCKED нужен, чтобы параллельный
        вызов не ждал тех же строк, а занялся остальными.
        """
        now = datetime.now(timezone.utc)
        stale = (
            await self._session.scalars(
                select(Reservation)
                .where(
                    Reservation.status == ReservationStatus.CREATED,
                    Reservation.pickup_deadline <= now,
                )
                .with_for_update(skip_locked=True)
            )
        ).all()
        for reservation in stale:
            await self._release_copy(reservation, ReservationStatus.EXPIRED)
        return len(stale)

    # ------------------------------------------------------------------
    # основные операции
    # ------------------------------------------------------------------

    async def reserve(self, user_id: int, book_id: int) -> Reservation:
        """Бронирует свободный экземпляр книги за читателем.

        Порядок проверок выбран так, чтобы читатель получал самую
        содержательную причину отказа: сначала правила, которые зависят
        от него самого, и только в конце наличие экземпляра на полке.
        """
        await self.expire_stale_pickups()

        book = await self._session.get(Book, book_id)
        if book is None:
            raise BookNotFound(f"Книга {book_id} не найдена")
        if book.status is not BookStatus.PUBLISHED:
            raise BookNotPublished(
                f"Книга «{book.title}» не опубликована, бронировать её нельзя"
            )

        if not await self._subscriptions.has_active(user_id):
            raise NoActiveSubscription(
                "Бронирование доступно только по действующей подписке"
            )
        if await self.has_overdue(user_id):
            raise HasOverdueLoan(
                "Сначала верните книгу, срок чтения которой истёк"
            )
        if await self._fines.has_unpaid(user_id):
            raise HasUnpaidFine("Сначала оплатите начисленный штраф")

        limit = self._settings.max_active_reservations
        if await self.active_count(user_id) >= limit:
            raise TooManyReservations(
                f"Одновременно можно держать не больше {limit} книг"
            )
        if await self._holds_book(user_id, book_id):
            raise AlreadyReserved(
                f"Экземпляр книги «{book.title}» уже закреплён за вами"
            )

        copy = await self._copies.lock_free_copy(book_id)
        if copy is None:
            raise NoCopyAvailable(
                f"Свободных экземпляров книги «{book.title}» сейчас нет"
            )

        now = datetime.now(timezone.utc)
        reservation = Reservation(
            user_id=user_id,
            copy_id=copy.id,
            status=ReservationStatus.CREATED,
            pickup_deadline=now
            + timedelta(hours=self._settings.reservation_hours),
        )
        copy.status = CopyStatus.RESERVED
        self._session.add(reservation)
        await self._session.flush()
        return reservation

    async def cancel(self, reservation_id: int) -> Reservation:
        """Читатель отказывается от брони до получения книги."""
        reservation = await self._lock(reservation_id)
        if reservation.status is not ReservationStatus.CREATED:
            raise InvalidReservationState(
                f"Отменить можно только бронь в статусе CREATED, "
                f"а эта в статусе {reservation.status.value}"
            )
        await self._release_copy(reservation, ReservationStatus.CANCELLED)
        return reservation

    async def issue(self, reservation_id: int) -> Reservation:
        """Библиотекарь выдаёт забронированный экземпляр на руки."""
        reservation = await self._lock(reservation_id)
        if reservation.status is not ReservationStatus.CREATED:
            raise InvalidReservationState(
                f"Выдать можно только бронь в статусе CREATED, "
                f"а эта в статусе {reservation.status.value}"
            )

        now = datetime.now(timezone.utc)
        if reservation.pickup_deadline <= now:
            # Срок получения истёк прямо перед выдачей: закрываем бронь,
            # экземпляр возвращается на полку.
            await self._release_copy(reservation, ReservationStatus.EXPIRED)
            raise PickupExpired(
                "Срок получения брони истёк, экземпляр вернулся в свободные"
            )

        copy = await self._session.get(
            BookCopy, reservation.copy_id, with_for_update=True
        )
        if copy is not None:
            copy.status = CopyStatus.ISSUED
        reservation.status = ReservationStatus.ISSUED
        reservation.issued_at = now
        reservation.due_date = now + timedelta(days=self._settings.loan_days)
        await self._session.flush()
        return reservation

    async def return_book(
        self, reservation_id: int
    ) -> tuple[Reservation, Fine | None]:
        """Библиотекарь принимает книгу. При просрочке начисляется пеня."""
        reservation = await self._lock(reservation_id)
        if reservation.status is not ReservationStatus.ISSUED:
            raise InvalidReservationState(
                f"Принять можно только выданную книгу, "
                f"а бронь в статусе {reservation.status.value}"
            )

        reservation.status = ReservationStatus.RETURNED
        reservation.returned_at = datetime.now(timezone.utc)
        copy = await self._session.get(
            BookCopy, reservation.copy_id, with_for_update=True
        )
        if copy is not None:
            copy.status = CopyStatus.AVAILABLE
        await self._session.flush()

        fine = await self._fines.charge_late_return(reservation)
        return reservation, fine

    async def mark_lost(self, reservation_id: int) -> tuple[Reservation, Fine]:
        """Библиотекарь фиксирует утерю выданного экземпляра."""
        reservation = await self._lock(reservation_id)
        if reservation.status is not ReservationStatus.ISSUED:
            raise InvalidReservationState(
                f"Утерю отмечают только для выданной книги, "
                f"а бронь в статусе {reservation.status.value}"
            )

        reservation.status = ReservationStatus.LOST
        copy = await self._session.get(
            BookCopy, reservation.copy_id, with_for_update=True
        )
        if copy is not None:
            copy.status = CopyStatus.LOST
        await self._session.flush()

        fine = await self._fines.charge_lost(reservation)
        return reservation, fine

    async def list_for_user(self, user_id: int) -> Sequence[Reservation]:
        return (
            await self._session.scalars(
                select(Reservation)
                .where(Reservation.user_id == user_id)
                .order_by(Reservation.created_at)
            )
        ).all()
