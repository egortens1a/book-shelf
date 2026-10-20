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

ACTIVE = UserStatus.ACTIVE
USERS = [  # логин, роль, статус
    ("admin", R.ADMIN, ACTIVE), ("librarian", R.LIBRARIAN, ACTIVE),
    ("reader", R.READER, ACTIVE), ("blocked", R.READER, UserStatus.BLOCKED),
    ("reader2", R.READER, ACTIVE), ("reader3", R.READER, ACTIVE),
    ("reader4", R.READER, ACTIVE), ("reader5", R.READER, ACTIVE),
    ("reader6", R.READER, ACTIVE), ("reader7", R.READER, ACTIVE),
]

# Классика должна оставаться первым жанром: демо берёт жанр по порядку создания.
BOOKS = [  # название, автор, жанр, доступ, статус
    # --- Классика ---
    ("Преступление и наказание", "Фёдор Достоевский", "Классика", A.FREE, S.PUBLISHED),
    ("Собачье сердце", "Михаил Булгаков", "Классика", A.FREE, S.PUBLISHED),
    ("Анна Каренина", "Лев Толстой", "Классика", A.SUBSCRIPTION, S.PUBLISHED),
    ("Капитанская дочка", "Александр Пушкин", "Классика", A.FREE, S.PUBLISHED),
    ("Мёртвые души", "Николай Гоголь", "Классика", A.FREE, S.PUBLISHED),
    ("Отцы и дети", "Иван Тургенев", "Классика", A.FREE, S.PUBLISHED),
    ("Энциклопедия 1990", "Станислав Лем", "Классика", A.FREE, S.ARCHIVED),
    # --- Фантастика ---
    ("Основание", "Айзек Азимов", "Фантастика", A.SUBSCRIPTION, S.PUBLISHED),
    ("Дюна", "Фрэнк Герберт", "Фантастика", A.SUBSCRIPTION, S.PUBLISHED),
    ("Солярис", "Станислав Лем", "Фантастика", A.FREE, S.PUBLISHED),
    ("451 градус по Фаренгейту", "Рэй Брэдбери", "Фантастика", A.FREE, S.PUBLISHED),
    ("Мы", "Евгений Замятин", "Фантастика", A.FREE, S.PUBLISHED),
    ("Пикник на обочине", "Аркадий и Борис Стругацкие", "Фантастика", A.SUBSCRIPTION, S.PUBLISHED),
    # --- Детектив ---
    ("Убийство в Восточном экспрессе", "Агата Кристи", "Детектив", A.SUBSCRIPTION, S.PUBLISHED),
    ("Собака Баскервилей", "Артур Конан Дойл", "Детектив", A.FREE, S.PUBLISHED),
    ("Заготовка без текста", "Агата Кристи", "Детектив", A.NONE, S.DRAFT),
    ("Заготовка без текста123", "Агата Кристи123", "Детектив", A.FREE, S.PUBLISHED),
    ("Заготовка без текста124", "Агата", "Детектив", A.FREE, S.PUBLISHED),
    ("Заготовка без текста125", "Дюма", "Детектив", A.FREE, S.PUBLISHED),
    ("Заготовка без текста126", "НеДюма", "Детектив", A.FREE, S.PUBLISHED),
]
TITLES = [b[0] for b in BOOKS]

# Оценки: книга -> {читатель: балл}. Подобраны так, чтобы топ было на что смотреть:
#  * «Отцы и дети» и «Пикник на обочине» - 10.0, но всего по одной оценке
#    (видно, зачем нужен min_ratings);
#  * «Дюна» и «Солярис» - одинаковые 9.5, но у «Дюны» оценок больше (порядок по числу оценок);
#  * «Основание» и «451 градус» - одинаковые 8.0, снова решает число оценок;
#  * «Энциклопедия 1990» - 10.0, но книга в архиве и в топ не попадает.
RATINGS = {
    "Собачье сердце": {"reader": 10, "reader2": 10, "reader3": 9, "reader4": 10, "reader5": 9},
    "Преступление и наказание": {"reader": 9, "reader2": 9, "reader3": 10, "reader6": 8},
    "Анна Каренина": {"reader2": 9, "reader3": 9, "reader4": 8, "reader5": 9, "reader7": 9},
    "Капитанская дочка": {"reader": 8, "reader4": 9},
    "Мёртвые души": {"reader3": 7, "reader5": 8, "reader6": 7},
    "Отцы и дети": {"reader7": 10},
    "Энциклопедия 1990": {"reader": 10, "reader2": 10},
    "Дюна": {"reader": 10, "reader2": 9, "reader3": 10, "reader5": 9, "reader6": 10, "reader7": 9},
    "Солярис": {"reader2": 10, "reader4": 9, "reader6": 9, "reader7": 10},
    "Основание": {"reader3": 8, "reader4": 7, "reader5": 9, "reader6": 8},
    "451 градус по Фаренгейту": {"reader": 9, "reader3": 8, "reader7": 7},
    "Мы": {"reader4": 6, "reader5": 7},
    "Пикник на обочине": {"reader2": 10},
    "Убийство в Восточном экспрессе": {"reader": 9, "reader3": 9, "reader5": 10},
    "Собака Баскервилей": {"reader2": 8, "reader6": 9},
}
COMMENTS = {("Преступление и наказание", "reader"): "Сильная книга"}

INTERESTS = {  # читатель -> интересные жанры
    "reader": ["Классика"], "reader2": ["Фантастика"],
    "reader3": ["Классика", "Детектив"], "reader4": ["Фантастика"],
}


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

    # Оценка ставится после прочтения, поэтому у каждой оценки есть завершённое чтение.
    finished = datetime.now(timezone.utc)
    for title, scores in RATINGS.items():
        book_id, text_len = books[title]
        for login, score in scores.items():
            user_id = users[login].id
            session.add_all([
                ReadingProgress(user_id=user_id, book_id=book_id, position=text_len,
                                finished_at=finished),
                Rating(user_id=user_id, book_id=book_id, score=score,
                       comment=COMMENTS.get((title, login))),
            ])

    for login, genre_names in INTERESTS.items():
        for name in genre_names:
            genre = await _get_or_create(session, Genre, Genre.name, name)
            session.add(UserGenre(user_id=users[login].id, genre_id=genre.id))

    session.add(WishlistItem(user_id=users["reader"].id, book_id=books["Основание"][0]))


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