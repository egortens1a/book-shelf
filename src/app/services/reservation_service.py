from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import BookStatus, CopyStatus, Fine, Reservation, ReservationStatus
from app.repositories import (
    BookCopyRepository,
    BookRepository,
    FineRepository,
    ReservationRepository,
)
from app.services.base import BaseService
from app.services.book_copy_service import BookCopyService
from app.core.errors import (
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
    UserNotFound,
)
from app.services.fine_service import FineService
from app.services.subscription_service import SubscriptionService


class ReservationService(BaseService):
    """Бронирование бумажных экземпляров, выдача, возврат и утеря.

    Сервис не фиксирует транзакцию. Это важно именно здесь: бронирование
    меняет и бронь, и экземпляр, и обе записи должны уехать в базу вместе.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.reservation_repo = ReservationRepository(session)
        self.copy_repo = BookCopyRepository(session)
        self.book_repo = BookRepository(session)
        self.fine_repo = FineRepository(session)
        self._settings = get_settings()
        self._subscriptions = SubscriptionService(session)
        self._copies = BookCopyService(session)
        self._fines = FineService(session)

    # ------------------------------------------------------------------
    # вспомогательное
    # ------------------------------------------------------------------

    async def _lock(self, reservation_id: int) -> Reservation:
        reservation = await self.reservation_repo.get_for_update(reservation_id)
        if reservation is None:
            raise ReservationNotFound(f"Бронь {reservation_id} не найдена")
        return reservation

    async def _release_copy(
        self, reservation: Reservation, status: ReservationStatus
    ) -> None:
        """Закрывает бронь и возвращает экземпляр в свободные."""
        reservation.status = status
        copy = await self.copy_repo.get_for_update(reservation.copy_id)
        if copy is not None and copy.status is CopyStatus.RESERVED:
            copy.status = CopyStatus.AVAILABLE
        await self.session.flush()

    async def active_count(self, user_id: int) -> int:
        """Сколько броней и выдач у читателя на руках прямо сейчас."""
        count = await self.reservation_repo.count_active(user_id)
        if count is None: raise UserNotFound
        return count

    async def has_overdue(self, user_id: int) -> bool:
        """Есть ли невозвращённая книга с истёкшим сроком чтения."""
        return await self.reservation_repo.has_overdue(
            user_id, datetime.now(timezone.utc)
        )

    async def has_returned(self, user_id: int, book_id: int) -> bool:
        """True, если читатель брал бумажный экземпляр книги и вернул его.

        Подходит под протокол ReturnedBookChecker блока А. Утерянная книга
        возвращённой не считается: такая бронь закрывается статусом LOST.
        """
        return await self.reservation_repo.has_returned(user_id, book_id)

    # ------------------------------------------------------------------
    # ленивое истечение
    # ------------------------------------------------------------------

    async def expire_stale_pickups(self) -> int:
        """Закрывает брони, которые не забрали в срок, и освобождает экземпляры.

        Планировщика в проекте нет: вместо него истечение выполняется при
        обращении к бронированию.
        """
        async with self._transaction():
            stale = await self.reservation_repo.lock_stale_pickups(
                datetime.now(timezone.utc)
            )
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

        async with self._transaction():
            # Блокировка строки читателя до конца транзакции. Без неё один
            # читатель из двух сессий проходит проверку лимита дважды: обе
            # видят одно и то же число активных броней и обе создают новую.
            if await self.user_repo.get_for_update(user_id) is None:
                raise UserNotFound(f"Пользователь {user_id} не найден")

            book = await self.book_repo.get_by_id(book_id)
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
            if await self.fine_repo.has_unpaid(user_id):
                raise HasUnpaidFine("Сначала оплатите начисленный штраф")

            limit = self._settings.max_active_reservations
            if await self.active_count(user_id) >= limit:
                raise TooManyReservations(
                    f"Одновременно можно держать не больше {limit} книг"
                )
            if await self.reservation_repo.holds_book(user_id, book_id):
                raise AlreadyReserved(
                    f"Экземпляр книги «{book.title}» уже закреплён за вами"
                )

            copy = await self.copy_repo.lock_free(book_id)
            if copy is None:
                raise NoCopyAvailable(
                    f"Свободных экземпляров книги «{book.title}» сейчас нет"
                )
            copy.status = CopyStatus.RESERVED
            try:
                return await self.reservation_repo.create(
                    user_id=user_id,
                    copy_id=copy.id,
                    pickup_deadline=datetime.now(timezone.utc)
                    + timedelta(hours=self._settings.reservation_hours),
                )
            except IntegrityError as exc:
                # Последний рубеж: uq_reservations_copy_active. Сработать почти
                # не может - экземпляр уже заблокирован через SKIP LOCKED, - но
                # без перевода в доменную ошибку клиент получил бы 500.
                raise NoCopyAvailable(
                    f"Экземпляр книги «{book.title}» только что заняли"
                ) from exc

    async def cancel(self, reservation_id: int, user_id: int) -> Reservation:
        """Читатель отказывается от брони до получения книги.

        Чужая бронь отдаётся как ненайденная, а не как запрещённая: иначе
        перебором по id можно выяснить, какие брони существуют.
        """
        async with self._transaction():
            reservation = await self._lock(reservation_id)
            if reservation.user_id != user_id:
                raise ReservationNotFound(f"Бронь {reservation_id} не найдена")
            if reservation.status is not ReservationStatus.CREATED:
                raise InvalidReservationState(
                    f"Отменить можно только бронь в статусе CREATED, "
                    f"а эта в статусе {reservation.status.value}"
                )
            await self._release_copy(reservation, ReservationStatus.CANCELLED)
            return reservation

    async def issue(self, reservation_id: int) -> Reservation:
        """Библиотекарь выдаёт забронированный экземпляр на руки."""
        expired = False
        async with self._transaction():
            reservation = await self._lock(reservation_id)
            if reservation.status is not ReservationStatus.CREATED:
                raise InvalidReservationState(
                    f"Выдать можно только бронь в статусе CREATED, "
                    f"а эта в статусе {reservation.status.value}"
                )

            now = datetime.now(timezone.utc)
            if reservation.pickup_deadline <= now:
                # Срок получения истёк: закрываем бронь, экземпляр возвращается
                # на полку. Сообщаем об этом после выхода из точки сохранения,
                # чтобы изменение не откатилось вместе с исключением.
                await self._release_copy(reservation, ReservationStatus.EXPIRED)
                expired = True
            else:
                copy = await self.copy_repo.get_for_update(reservation.copy_id)
                if copy is not None:
                    copy.status = CopyStatus.ISSUED
                reservation.status = ReservationStatus.ISSUED
                reservation.issued_at = now
                reservation.due_date = now + timedelta(
                    days=self._settings.loan_days
                )
                await self.session.flush()

        if expired:
            raise PickupExpired(
                "Срок получения брони истёк, экземпляр вернулся в свободные"
            )
        return reservation

    async def return_book(
        self, reservation_id: int
    ) -> tuple[Reservation, Fine | None]:
        """Библиотекарь принимает книгу. При просрочке начисляется пеня."""
        async with self._transaction():
            reservation = await self._lock(reservation_id)
            if reservation.status is not ReservationStatus.ISSUED:
                raise InvalidReservationState(
                    f"Принять можно только выданную книгу, "
                    f"а бронь в статусе {reservation.status.value}"
                )

            reservation.status = ReservationStatus.RETURNED
            reservation.returned_at = datetime.now(timezone.utc)
            copy = await self.copy_repo.get_for_update(reservation.copy_id)
            if copy is not None:
                copy.status = CopyStatus.AVAILABLE
            await self.session.flush()

        fine = await self._fines.charge_late_return(reservation)
        return reservation, fine

    async def mark_lost(self, reservation_id: int) -> tuple[Reservation, Fine]:
        """Библиотекарь фиксирует утерю выданного экземпляра."""
        async with self._transaction():
            reservation = await self._lock(reservation_id)
            if reservation.status is not ReservationStatus.ISSUED:
                raise InvalidReservationState(
                    f"Утерю отмечают только для выданной книги, "
                    f"а бронь в статусе {reservation.status.value}"
                )

            reservation.status = ReservationStatus.LOST
            copy = await self.copy_repo.get_for_update(reservation.copy_id)
            if copy is not None:
                copy.status = CopyStatus.LOST
            await self.session.flush()

        fine = await self._fines.charge_lost(reservation)
        return reservation, fine

    async def get_card(self, reservation_id: int) -> Reservation:
        """Бронь с экземпляром и книгой, готовая к отдаче клиенту."""
        reservation = await self.reservation_repo.get_card(reservation_id)
        if reservation is None:
            raise ReservationNotFound(f"Бронь {reservation_id} не найдена")
        return reservation

    async def list_for_user(self, user_id: int) -> list[Reservation]:
        """История броней читателя, от новых к старым."""
        return await self.reservation_repo.list_by_user(user_id)

    async def list_filtered(
        self,
        status: ReservationStatus | None = None,
        user_id: int | None = None,
        inventory_number: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Reservation]:
        """Список броней для библиотекаря. Размер страницы зажат в разумные рамки."""
        return await self.reservation_repo.list_filtered(
            status=status,
            user_id=user_id,
            inventory_number=inventory_number,
            limit=max(1, min(limit, 200)),
            offset=max(0, offset),
        )
