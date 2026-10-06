"""Демонстрация работы с БД по сценариям блока Б.

Проходит сценарии 4, 8, 9 и 10 из технического задания: подписка,
бронирование, выдача с возвратом, просрочка со штрафом. Перед прогоном
база приводится к состоянию seed, поэтому скрипт можно запускать
повторно и получать один и тот же результат.

Запуск:  python src/app/scripts/demo_loans.py
"""

import asyncio

from sqlalchemy import select

from app.core.db import engine, session_factory
from app.models import Book, Reservation, User
from app.scripts.seed_loans import clear_previous, seed
from app.services.book_copy import BookCopyService
from app.services.errors import ServiceError
from app.services.fine import FineService
from app.services.reservation import ReservationService
from app.services.subscription import SubscriptionService

# В db.py echo зашит жёстко, иначе вывод тонет в SQL.
engine.echo = False


def head(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def step(text: str) -> None:
    print(f"\n-- {text}")


async def expect_refusal(coro, note: str) -> None:
    """Ожидаемый отказ: печатает причину, которую вернул сервис."""
    try:
        await coro
        print(f"   {note}: ПРОБЛЕМА, операция прошла")
    except ServiceError as exc:
        print(f"   {note}: отказ - {exc}")


async def main() -> None:
    async with session_factory() as session:
        await clear_previous(session)
        await seed(session)
        await session.commit()
        print("База приведена к исходному состоянию.")

        users = {
            u.email.split("@")[0]: u
            for u in (await session.scalars(select(User))).all()
        }
        books = {b.title: b for b in (await session.scalars(select(Book))).all()}

        subscriptions = SubscriptionService(session)
        reservations = ReservationService(session)
        copies = BookCopyService(session)
        fines = FineService(session)

        anna = users["anna"]
        boris = users["boris"]
        vera = users["vera"]
        grigory = users["grigory"]

        # ------------------------------------------------------------------
        head("Сценарий 4. Подписка")

        step("у Веры подписка закончилась")
        print(f"   подписка действует: {await subscriptions.has_active(vera.id)}")
        await expect_refusal(
            reservations.reserve(vera.id, books["Евгений Онегин"].id),
            "бронирование без подписки",
        )

        step("Вера оформляет подписку")
        fresh = await subscriptions.subscribe(vera.id)
        print(f"   создана подписка {fresh.status.value}: "
              f"{fresh.started_at:%d.%m.%Y} - {fresh.expires_at:%d.%m.%Y}")
        print(f"   подписка действует: {await subscriptions.has_active(vera.id)}")

        step("Анна продлевает подписку заранее")
        renewal = await subscriptions.subscribe(anna.id)
        print(f"   продление {renewal.status.value}: "
              f"{renewal.started_at:%d.%m.%Y} - {renewal.expires_at:%d.%m.%Y}")
        await expect_refusal(
            subscriptions.subscribe(anna.id), "второе продление в очередь"
        )
        await session.commit()

        # ------------------------------------------------------------------
        head("Сценарий 8. Бронирование")

        step("Анна бронирует «Войну и мир»")
        booked = await reservations.reserve(anna.id, books["Война и мир"].id)
        copy = await copies.get(booked.copy_id)
        print(f"   закреплён экземпляр {copy.inventory_number}, "
              f"забрать до {booked.pickup_deadline:%d.%m.%Y %H:%M}")

        step("проверка правил бронирования")
        await expect_refusal(
            reservations.reserve(anna.id, books["Война и мир"].id),
            "вторая бронь той же книги",
        )
        await expect_refusal(
            reservations.reserve(vera.id, books["Война и мир"].id),
            "свободных экземпляров не осталось",
        )
        await expect_refusal(
            reservations.reserve(anna.id, books["Чистый код"].id),
            "у книги нет бумажных экземпляров",
        )
        await session.commit()

        # ------------------------------------------------------------------
        head("Сценарий 9. Выдача и возврат")

        step("Борис забирает свою бронь")
        boris_reservation = await session.scalar(
            select(Reservation).where(Reservation.user_id == boris.id)
        )
        issued = await reservations.issue(boris_reservation.id)
        print(f"   выдана, вернуть до {issued.due_date:%d.%m.%Y}")

        step("Борис возвращает книгу вовремя")
        returned, fine = await reservations.return_book(issued.id)
        print(f"   принята {returned.returned_at:%d.%m.%Y}, "
              f"штраф: {'нет' if fine is None else fine.amount}")
        print(f"   экземпляр снова свободен: "
              f"{(await copies.get(returned.copy_id)).status.value}")
        await session.commit()

        # ------------------------------------------------------------------
        head("Сценарий 10. Просрочка и штраф")

        overdue = await session.scalar(
            select(Reservation).where(Reservation.user_id == grigory.id)
        )
        step("у Григория книга на руках сверх срока")
        print(f"   вернуть надо было {overdue.due_date:%d.%m.%Y}")
        print(f"   просрочено суток: {fines.overdue_days(overdue)}")
        print(f"   расчётная пеня: {fines.accrued_amount(overdue)} "
              f"(в базе не хранится)")

        await expect_refusal(
            reservations.reserve(grigory.id, books["Евгений Онегин"].id),
            "бронирование при просроченной книге",
        )

        step("библиотекарь принимает просроченную книгу")
        _, late_fine = await reservations.return_book(overdue.id)
        print(f"   начислен штраф {late_fine.amount} "
              f"по причине {late_fine.reason.value}, статус {late_fine.status.value}")

        await expect_refusal(
            reservations.reserve(grigory.id, books["Евгений Онегин"].id),
            "бронирование с неоплаченным штрафом",
        )

        step("Григорий оплачивает штраф")
        paid = await fines.pay(late_fine.id)
        print(f"   штраф {paid.amount}: {paid.status.value} "
              f"({paid.paid_at:%d.%m.%Y %H:%M})")
        allowed = await reservations.reserve(
            grigory.id, books["Евгений Онегин"].id
        )
        print(f"   бронирование снова доступно, бронь {allowed.id} "
              f"в статусе {allowed.status.value}")
        await session.commit()

        # ------------------------------------------------------------------
        head("Утеря экземпляра")

        step("Анна получает забронированную книгу и теряет её")
        issued_to_anna = await reservations.issue(booked.id)
        lost, lost_fine = await reservations.mark_lost(issued_to_anna.id)
        print(f"   бронь закрыта статусом {lost.status.value}")
        print(f"   экземпляр: "
              f"{(await copies.get(lost.copy_id)).status.value}")
        print(f"   штраф {lost_fine.amount} по причине {lost_fine.reason.value}")

        step("оценку за утерянную книгу поставить нельзя")
        print(f"   has_returned(Анна, «Война и мир») = "
              f"{await reservations.has_returned(anna.id, books['Война и мир'].id)}")
        print(f"   has_returned(Борис, «Война и мир») = "
              f"{await reservations.has_returned(boris.id, books['Война и мир'].id)}")
        await session.commit()

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
