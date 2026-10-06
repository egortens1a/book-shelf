"""Тестовые данные для блока Б: подписки, экземпляры, брони.

Скрипт идемпотентен: при каждом запуске удаляет созданные им ранее записи
и наполняет базу заново. Данные блока А (жанры, авторы, оценки) не трогает.

Запуск:  python src/app/scripts/seed_loans.py
"""

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import bcrypt
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import engine, session_factory
from app.models import (
    AccessType,
    Book,
    BookCopy,
    BookStatus,
    CopyStatus,
    Fine,
    Reservation,
    ReservationStatus,
    Role,
    RoleTypes,
    Subscription,
    SubscriptionStatus,
    User,
)

# Пароль только для тестовых данных, в рабочей среде не используется.
SEED_PASSWORD = "seed-password"
SEED_DOMAIN = "@loans.seed"

SEED_BOOK_TITLES = [
    "Война и мир",
    "Мастер и Маргарита",
    "Евгений Онегин",
    "Чистый код",
]


def hash_password(raw: str) -> str:
    return bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()


async def clear_previous(session: AsyncSession) -> None:
    """Удаляет данные прошлого запуска в порядке, допустимом внешними ключами."""
    user_ids = (
        select(User.id).where(User.email.like(f"%{SEED_DOMAIN}"))
    ).scalar_subquery()
    book_ids = (
        select(Book.id).where(Book.title.in_(SEED_BOOK_TITLES))
    ).scalar_subquery()
    reservation_ids = (
        select(Reservation.id).where(Reservation.user_id.in_(user_ids))
    ).scalar_subquery()

    await session.execute(delete(Fine).where(Fine.reservation_id.in_(reservation_ids)))
    await session.execute(delete(Reservation).where(Reservation.user_id.in_(user_ids)))
    await session.execute(delete(Subscription).where(Subscription.user_id.in_(user_ids)))
    await session.execute(delete(BookCopy).where(BookCopy.book_id.in_(book_ids)))
    await session.execute(delete(User).where(User.email.like(f"%{SEED_DOMAIN}")))
    await session.execute(delete(Book).where(Book.title.in_(SEED_BOOK_TITLES)))


async def get_role(session: AsyncSession, name: RoleTypes) -> Role:
    """Роль ищется по имени, а не по идентификатору: порядок вставки в миграции
    не гарантирован и может измениться."""
    role = await session.scalar(select(Role).where(Role.name == name))
    if role is None:
        raise RuntimeError(
            f"В базе нет роли {name.value}. Сначала примените миграции: alembic upgrade head"
        )
    return role


async def seed(session: AsyncSession) -> None:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    month = timedelta(days=30)
    password_hash = hash_password(SEED_PASSWORD)

    reader = await get_role(session, RoleTypes.READER)
    librarian = await get_role(session, RoleTypes.LIBRARIAN)

    # --- пользователи ---------------------------------------------------
    anna = User(full_name="Анна Читаева", email=f"anna{SEED_DOMAIN}",
                password_hash=password_hash, role_id=reader.id)
    boris = User(full_name="Борис Листаев", email=f"boris{SEED_DOMAIN}",
                 password_hash=password_hash, role_id=reader.id)
    vera = User(full_name="Вера Полкина", email=f"vera{SEED_DOMAIN}",
                password_hash=password_hash, role_id=reader.id)
    grigory = User(full_name="Григорий Должников", email=f"grigory{SEED_DOMAIN}",
                   password_hash=password_hash, role_id=reader.id)
    maria = User(full_name="Мария Выдачина", email=f"maria{SEED_DOMAIN}",
                 password_hash=password_hash, role_id=librarian.id)
    session.add_all([anna, boris, vera, grigory, maria])
    await session.flush()

    # --- книги ----------------------------------------------------------
    # У книги с access_type=NONE электронной версии нет, text_content пустой.
    war_and_peace = Book(
        title="Война и мир",
        description="Роман-эпопея о русском обществе в эпоху войн против Наполеона.",
        publication_year=1869,
        access_type=AccessType.NONE,
        status=BookStatus.PUBLISHED,
        text_content=None,
    )
    master = Book(
        title="Мастер и Маргарита",
        description="Роман о визите дьявола в Москву тридцатых годов.",
        publication_year=1967,
        access_type=AccessType.SUBSCRIPTION,
        status=BookStatus.PUBLISHED,
        text_content="Глава первая. Никогда не разговаривайте с неизвестными...",
    )
    onegin = Book(
        title="Евгений Онегин",
        description="Роман в стихах, общественное достояние.",
        publication_year=1833,
        access_type=AccessType.FREE,
        status=BookStatus.PUBLISHED,
        text_content="Мой дядя самых честных правил...",
    )
    clean_code = Book(
        title="Чистый код",
        description="О том, как писать поддерживаемый код. Только в электронном виде.",
        publication_year=2008,
        access_type=AccessType.SUBSCRIPTION,
        status=BookStatus.PUBLISHED,
        text_content="Глава 1. Чистый код...",
    )
    session.add_all([war_and_peace, master, onegin, clean_code])
    await session.flush()

    # --- экземпляры -----------------------------------------------------
    # У «Чистого кода» бумажных экземпляров нет: бронировать нечего.
    copies = {
        "wp1": BookCopy(book_id=war_and_peace.id, inventory_number="INV-0001",
                        status=CopyStatus.AVAILABLE),
        "wp2": BookCopy(book_id=war_and_peace.id, inventory_number="INV-0002",
                        status=CopyStatus.RESERVED),
        "wp3": BookCopy(book_id=war_and_peace.id, inventory_number="INV-0003",
                        status=CopyStatus.WRITTEN_OFF),
        "ma1": BookCopy(book_id=master.id, inventory_number="INV-0004",
                        status=CopyStatus.ISSUED),
        "ma2": BookCopy(book_id=master.id, inventory_number="INV-0005",
                        status=CopyStatus.AVAILABLE),
        "on1": BookCopy(book_id=onegin.id, inventory_number="INV-0006",
                        status=CopyStatus.AVAILABLE),
    }
    session.add_all(list(copies.values()))
    await session.flush()

    # --- подписки -------------------------------------------------------
    price = Decimal(settings.subscription_price)

    # Анна: обычная действующая подписка.
    session.add(Subscription(user_id=anna.id, price=price,
                             status=SubscriptionStatus.ACTIVE,
                             started_at=now - timedelta(days=5),
                             expires_at=now - timedelta(days=5) + month))

    # Борис: действующая подписка и оплаченное заранее продление.
    boris_expires = now + timedelta(days=3)
    session.add(Subscription(user_id=boris.id, price=price,
                             status=SubscriptionStatus.ACTIVE,
                             started_at=boris_expires - month,
                             expires_at=boris_expires))
    session.add(Subscription(user_id=boris.id, price=price,
                             status=SubscriptionStatus.PENDING,
                             started_at=boris_expires,
                             expires_at=boris_expires + month))

    # Вера: подписка закончилась, бронировать больше нельзя.
    session.add(Subscription(user_id=vera.id, price=price,
                             status=SubscriptionStatus.EXPIRED,
                             started_at=now - timedelta(days=40) - month,
                             expires_at=now - timedelta(days=40)))

    # Григорий: подписка действует, но на руках просроченная книга.
    session.add(Subscription(user_id=grigory.id, price=price,
                             status=SubscriptionStatus.ACTIVE,
                             started_at=now - timedelta(days=20),
                             expires_at=now - timedelta(days=20) + month))

    # --- брони ----------------------------------------------------------
    pickup = timedelta(hours=settings.reservation_hours)
    loan = timedelta(days=settings.loan_days)

    # Борис забронировал и ещё не забрал: экземпляр ждёт его на полке выдачи.
    session.add(Reservation(user_id=boris.id, copy_id=copies["wp2"].id,
                            status=ReservationStatus.CREATED,
                            created_at=now - timedelta(hours=5),
                            pickup_deadline=now - timedelta(hours=5) + pickup))

    # Григорий держит книгу дольше срока: при возврате начислится пеня.
    grigory_issued = now - timedelta(days=20)
    session.add(Reservation(user_id=grigory.id, copy_id=copies["ma1"].id,
                            status=ReservationStatus.ISSUED,
                            created_at=grigory_issued - timedelta(hours=6),
                            pickup_deadline=grigory_issued - timedelta(hours=6) + pickup,
                            issued_at=grigory_issued,
                            due_date=grigory_issued + loan))

    # Анна когда-то не забрала бронь в срок.
    anna_old = now - timedelta(days=15)
    session.add(Reservation(user_id=anna.id, copy_id=copies["on1"].id,
                            status=ReservationStatus.EXPIRED,
                            created_at=anna_old,
                            pickup_deadline=anna_old + pickup))

    # Вера брала книгу, пока подписка действовала, и вернула вовремя.
    vera_issued = now - timedelta(days=60)
    session.add(Reservation(user_id=vera.id, copy_id=copies["on1"].id,
                            status=ReservationStatus.RETURNED,
                            created_at=vera_issued - timedelta(hours=2),
                            pickup_deadline=vera_issued - timedelta(hours=2) + pickup,
                            issued_at=vera_issued,
                            due_date=vera_issued + loan,
                            returned_at=vera_issued + timedelta(days=9)))

    # Штрафы не создаются: по ТЗ их начисляет сервис в момент возврата или утери.


async def report(session: AsyncSession) -> None:
    for model, label in (
        (User, "пользователи"),
        (Book, "книги"),
        (BookCopy, "экземпляры"),
        (Subscription, "подписки"),
        (Reservation, "брони"),
        (Fine, "штрафы"),
    ):
        rows = (await session.scalars(select(model))).all()
        print(f"  {label}: {len(rows)}")


async def main() -> None:
    async with session_factory() as session:
        await clear_previous(session)
        await seed(session)
        await session.commit()
        print("Тестовые данные блока Б загружены. В базе сейчас:")
        await report(session)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
