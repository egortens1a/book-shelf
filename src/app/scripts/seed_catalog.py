"""Тестовые данные блока А. Идемпотентно: свои записи удаляются и создаются заново.

Запуск (из каталога src):  python -m app.scripts.seed_catalog
"""
import asyncio
from datetime import datetime, timezone

from sqlalchemy import delete, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import engine, session_factory
from app.core.security import hash_password
from app.core.text import normalize_name
from app.models import (
    AccessType as A, Author, Book, BookAuthor, BookGenre, BookStatus as S, Genre, Rating,
    ReadingProgress, Role, RoleTypes as R, User, UserGenre, UserStatus, WishlistItem,
)

SEED_PASSWORD = "seed-password"  # только для тестовых данных
SEED_DOMAIN = "@catalog.seed"

USERS = [  # логин, роль, статус
    ("admin", R.ADMIN, UserStatus.ACTIVE), ("librarian", R.LIBRARIAN, UserStatus.ACTIVE),
    ("reader", R.READER, UserStatus.ACTIVE), ("blocked", R.READER, UserStatus.BLOCKED),
]
BOOKS = [  # название, автор, жанр, доступ, статус
    ("Преступление и наказание", "Фёдор Достоевский", "Классика", A.FREE, S.PUBLISHED),
    ("Основание", "Айзек Азимов", "Фантастика", A.SUBSCRIPTION, S.PUBLISHED),
    ("Энциклопедия 1990", "Станислав Лем", "Классика", A.FREE, S.ARCHIVED),
    ("Заготовка без текста", "Агата Кристи", "Детектив", A.NONE, S.DRAFT),
]
TITLES = [b[0] for b in BOOKS]


async def ensure_roles(session: AsyncSession) -> None:
    await session.execute(pg_insert(Role).values([{"name": r} for r in R])
                          .on_conflict_do_nothing(index_elements=[Role.name]))


async def clear_previous(session: AsyncSession) -> None:
    users = select(User.id).where(User.email.like(f"%{SEED_DOMAIN}")).scalar_subquery()
    books = select(Book.id).where(Book.title.in_(TITLES)).scalar_subquery()
    for m in (Rating, WishlistItem, ReadingProgress):
        await session.execute(delete(m).where(or_(m.user_id.in_(users), m.book_id.in_(books))))
    await session.execute(delete(UserGenre).where(UserGenre.user_id.in_(users)))
    for m in (BookAuthor, BookGenre):
        await session.execute(delete(m).where(m.book_id.in_(books)))
    await session.execute(delete(User).where(User.email.like(f"%{SEED_DOMAIN}")))
    await session.execute(delete(Book).where(Book.title.in_(TITLES)))


async def _get_or_create(session: AsyncSession, model, column, value: str):
    value = normalize_name(value)
    obj = await session.scalar(select(model).where(column == value))
    if obj is None:
        obj = model(**{column.key: value})
        session.add(obj)
        await session.flush()
    return obj


async def seed(session: AsyncSession) -> None:
    roles = {r.name: r.id for r in (await session.scalars(select(Role))).all()}
    password_hash = hash_password(SEED_PASSWORD)
    users = {}
    for login, role, status in USERS:
        users[login] = User(full_name=f"{login.capitalize()} Seed", email=f"{login}{SEED_DOMAIN}",
                            password_hash=password_hash, role_id=roles[role], status=status)
        session.add(users[login])

    books = {}  # название -> (id, длина текста)
    for title, author, genre, access, status in BOOKS:
        text = None if access == A.NONE else f"{title}. " + "Учебный текст. " * 30
        book = Book(title=title, description=f"Описание: {title}", access_type=access,
                    status=status, text_content=text)
        session.add(book)
        await session.flush()
        a = await _get_or_create(session, Author, Author.full_name, author)
        g = await _get_or_create(session, Genre, Genre.name, genre)
        session.add_all([BookAuthor(book_id=book.id, author_id=a.id),
                         BookGenre(book_id=book.id, genre_id=g.id)])
        books[title] = (book.id, len(text or ""))

    reader = users["reader"]
    crime_id, crime_len = books["Преступление и наказание"]
    classic = await _get_or_create(session, Genre, Genre.name, "Классика")
    session.add_all([
        UserGenre(user_id=reader.id, genre_id=classic.id),
        ReadingProgress(user_id=reader.id, book_id=crime_id, position=crime_len,
                        finished_at=datetime.now(timezone.utc)),
        Rating(user_id=reader.id, book_id=crime_id, score=9, comment="Сильная книга"),
        WishlistItem(user_id=reader.id, book_id=books["Основание"][0]),
    ])


async def report(session: AsyncSession) -> None:
    for model, label in ((Genre, "жанры"), (Author, "авторы"), (Rating, "оценки"),
                         (ReadingProgress, "прогресс чтения"), (WishlistItem, "хочу прочитать")):
        print(f"  {label}: {len((await session.scalars(select(model))).all())}")


async def main() -> None:
    async with session_factory() as session:
        await ensure_roles(session)
        await clear_previous(session)
        await seed(session)
        await session.commit()
        print("Данные блока А загружены:")
        await report(session)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())