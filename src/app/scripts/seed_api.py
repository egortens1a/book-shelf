"""Данные для демонстрации REST API (ЛР2): роли, учётные записи, жанры, книга.

Идемпотентно и без очистки базы: учётные записи приводятся к известному
состоянию (пароль, роль, статус ACTIVE), чужие данные не трогаются.
Книга для оценки создаётся один раз, у читателя из seed она уже дочитана
(оценка разрешена), а его прежняя оценка сбрасывается, чтобы демо
можно было запускать повторно.

Запуск (из каталога src):  python -m app.scripts.seed_api
"""
import asyncio
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import engine, session_factory
from app.core.security import hash_password
from app.models import (
    AccessType, Author, Book, BookAuthor, BookGenre, BookStatus, Genre, Rating,
    ReadingProgress, Role, RoleTypes, User, UserStatus,
)
from app.scripts.seed_catalog import _get_or_create, ensure_roles

# Пароли только для тестовых данных, в рабочей среде не используются.
ADMIN_EMAIL = "admin@bookshelf.local"
ADMIN_PASSWORD = "Admin-Pass-123"
LIBRARIAN_EMAIL = "librarian@bookshelf.local"
LIBRARIAN_PASSWORD = "Librarian-Pass-123"
READER_EMAIL = "reader@bookshelf.local"
READER_PASSWORD = "Reader-Pass-123"

ACCOUNTS = [  # email, имя, пароль, роль
    (ADMIN_EMAIL, "Администратор", ADMIN_PASSWORD, RoleTypes.ADMIN),
    (LIBRARIAN_EMAIL, "Библиотекарь", LIBRARIAN_PASSWORD, RoleTypes.LIBRARIAN),
    (READER_EMAIL, "Читатель", READER_PASSWORD, RoleTypes.READER),
]
GENRES = ["Классика", "Фантастика", "Детектив"]

# Опубликованная электронная книга, дочитанная читателем из seed.
RATED_BOOK_TITLE = "Книга для оценки API"
RATED_BOOK_AUTHOR = "Автор Тестовый"
RATED_BOOK_GENRE = "Классика"
RATED_BOOK_TEXT = "Учебный текст. " * 30


async def _upsert_user(
    session: AsyncSession, email: str, full_name: str, password: str, role_id: int
) -> User:
    user = await session.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email, full_name=full_name, role_id=role_id,
                    password_hash=hash_password(password), status=UserStatus.ACTIVE)
        session.add(user)
    else:  # повторный запуск возвращает известное состояние, в том числе разблокирует
        user.full_name = full_name
        user.role_id = role_id
        user.password_hash = hash_password(password)
        user.status = UserStatus.ACTIVE
    await session.flush()
    return user


async def _ensure_rated_book(session: AsyncSession, reader: User) -> Book:
    book = await session.scalar(select(Book).where(Book.title == RATED_BOOK_TITLE))
    if book is None:
        book = Book(title=RATED_BOOK_TITLE, description="Книга для проверки оценок через API",
                    access_type=AccessType.FREE, status=BookStatus.PUBLISHED,
                    text_content=RATED_BOOK_TEXT)
        session.add(book)
        await session.flush()
        author = await _get_or_create(session, Author, Author.full_name, RATED_BOOK_AUTHOR)
        genre = await _get_or_create(session, Genre, Genre.name, RATED_BOOK_GENRE)
        session.add_all([BookAuthor(book_id=book.id, author_id=author.id),
                         BookGenre(book_id=book.id, genre_id=genre.id)])
    else:
        book.status = BookStatus.PUBLISHED

    # Оценка разрешена после прочтения: у читателя есть завершённое чтение.
    progress = await session.scalar(select(ReadingProgress).where(
        ReadingProgress.user_id == reader.id, ReadingProgress.book_id == book.id))
    if progress is None:
        session.add(ReadingProgress(user_id=reader.id, book_id=book.id,
                                    position=len(RATED_BOOK_TEXT),
                                    finished_at=datetime.now(timezone.utc)))
    else:
        progress.position = len(RATED_BOOK_TEXT)
        progress.finished_at = datetime.now(timezone.utc)

    # Сбрасываем прошлую оценку, чтобы сценарий оценок повторялся с чистого листа.
    await session.execute(delete(Rating).where(
        Rating.user_id == reader.id, Rating.book_id == book.id))
    return book


async def ensure_seed(session: AsyncSession) -> None:
    await ensure_roles(session)
    roles = {r.name: r.id for r in (await session.scalars(select(Role))).all()}
    users = {}
    for email, full_name, password, role in ACCOUNTS:
        users[email] = await _upsert_user(session, email, full_name, password, roles[role])
    for name in GENRES:
        await _get_or_create(session, Genre, Genre.name, name)
    await _ensure_rated_book(session, users[READER_EMAIL])


async def main() -> None:
    async with session_factory() as session:
        await ensure_seed(session)
        await session.commit()
    print("Данные для REST API загружены. Учётные записи (логин = email):")
    for email, _, password, role in ACCOUNTS:
        print(f"  {role.value:<10} {email:<28} {password}")
    print(f"Книга для оценки: «{RATED_BOOK_TITLE}» (читатель из seed её дочитал)")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())