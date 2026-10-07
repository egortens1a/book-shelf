import asyncio
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace

from app.core.db import engine, session_factory
from app.models import AccessType
from app.repositories import AuthorRepository, GenreRepository, UserRepository
from app.services.book_copy import BookCopyService
from app.services.catalog_service import CatalogService
from app.services.directory_service import DirectoryService
from app.services.rating_service import RatingService
from app.services.reading_service import ReadingService
from app.services.reservation import ReservationService
from app.services.stats_service import StatsService
from app.services.subscription import SubscriptionService
from app.services.user_service import UserService
from app.services.wishlist_service import WishlistService

PASSWORD = "demo-password-1"
TEXT = "Учебный текст книги. " * 20


def ok(msg: str) -> None:
    print(f"  [OK]    {msg}")


async def refuse(label: str, coro, exc=ValueError) -> None:
    try:
        await coro
    except exc as e:
        print(f"  [ОТКАЗ] {label}: {e}")
    else:
        raise AssertionError(f"Ожидался отказ: {label}")


@asynccontextmanager
async def services(sf):
    async with sf() as s:
        subs, res = SubscriptionService(s), ReservationService(s)
        yield SimpleNamespace(
            session=s, subs=subs, res=res, copies=BookCopyService(s),
            users=UserService(s), catalog=CatalogService(s), directory=DirectoryService(s),
            reading=ReadingService(s, subs.has_active), rating=RatingService(s, res.has_returned),
            wishlist=WishlistService(s), stats=StatsService(s),
        )


async def run_block_a(sf=session_factory) -> None:
    tag = uuid.uuid4().hex[:6]
    try:
        async with sf() as s:
            admin = (await UserRepository(s).get_by_email("admin@catalog.seed")).id
            classic = (await GenreRepository(s).get_by_name("Классика")).id
            lem = (await AuthorRepository(s).get_by_full_name("Станислав Лем")).id
    except AttributeError:
        raise RuntimeError("Сначала загрузите данные: python -m app.scripts.seed") from None

    async with services(sf) as sv:
        print("\n1. Пользователи и справочники")
        reader = await sv.users.register_reader("  Анна   Иванова ", f"Anna.{tag}@Example.com", PASSWORD, [classic])
        r1, email = reader.id, reader.email
        ok(f"регистрация: {reader.full_name}, {email}")
        await refuse("повторный email", sv.users.register_reader("Аня", email.upper(), PASSWORD))
        await refuse("короткий пароль", sv.users.register_reader("Т", f"x.{tag}@example.com", "123"))
        email2 = f"boris.{tag}@example.com"
        r2 = (await sv.users.register_reader("Борис", email2, PASSWORD)).id
        await sv.users.block_user(admin, r2)
        await refuse("вход заблокированного", sv.users.authenticate(email2, PASSWORD), PermissionError)
        await sv.users.unblock_user(admin, r2)
        await sv.users.authenticate(email2, PASSWORD)
        ok("после разблокировки вход работает")
        await refuse("читатель правит справочник", sv.directory.create_genre(r1, "Хак"), PermissionError)
        genre = await sv.directory.create_genre(admin, f"  временный   жанр {tag} ")
        genre_id = genre.id
        ok(f"жанр нормализован: {genre.name}")
        await refuse("дубликат жанра", sv.directory.create_genre(admin, f"Временный Жанр {tag}"))
        await sv.directory.delete_genre(admin, genre_id)

        print("\n2. Каталог ")
        await refuse("FREE без текста", sv.catalog.create_book_draft(
            "Без текста", "Описание", [lem], [classic], AccessType.FREE))
        free = (await sv.catalog.create_book_draft(
            f"Электронная {tag}", "Описание", [lem], [classic], AccessType.FREE, text_content=TEXT)).id
        sub = (await sv.catalog.create_book_draft(
            f"Подписная {tag}", "Описание", [lem], [classic], AccessType.SUBSCRIPTION, text_content=TEXT)).id
        assert await sv.catalog.search_books(title=tag) == []
        ok("черновики не видны читателю")
        await sv.catalog.publish_book(free)
        await sv.catalog.publish_book(sub)
        assert {b.id for b in await sv.catalog.search_books(title=tag)} == {free, sub}
        ok("опубликованные книги находятся поиском")
        await refuse("повторная публикация", sv.catalog.publish_book(free))
        await refuse("удаление опубликованной книги", sv.catalog.delete_draft(free))

        print("\n3. Чтение и оценки (подписка из блока Б)")
        n = len(TEXT)
        await sv.subs.subscribe(r1)
        await sv.session.commit()
        await refuse("подписная книга без подписки", sv.reading.open_for_reading(r2, sub))
        await sv.reading.save_position(r1, sub, 5)
        ok("с подпиской подписная книга читается")
        await sv.reading.save_position(r1, free, n // 2)
        await refuse("позиция за пределами текста", sv.reading.save_position(r1, free, n + 1))
        await refuse("оценка недочитанной книги", sv.rating.rate(r1, free, 9))
        assert (await sv.reading.save_position(r1, free, n)).finished_at is not None
        rating = await sv.rating.rate(r1, free, 9, " Отлично ")
        ok(f"дочитал и оценил: {rating.score}, {rating.comment}")
        await refuse("оценка 11", sv.rating.rate(r1, free, 11))
        summary = await sv.rating.get_book_summary(free)
        assert (summary.count, summary.average) == (1, 9.0)
        ok("сводка: 1 оценка, средний балл 9.0")
        assert await sv.wishlist.add(r1, sub) and not await sv.wishlist.add(r1, sub)
        ok("в хочу прочитать дубликат не добавляется")

        print("\n4. Бумажная книга (стык с блоком Б)")
        paper = (await sv.catalog.create_book_draft(
            f"Бумажная {tag}", "Есть только на бумаге", [lem], [classic])).id
        await refuse("публикация без текста и без экземпляров", sv.catalog.publish_book(paper))
        await sv.copies.register(paper, f"DEMO-{tag}-1")
        await sv.session.commit()
        await sv.catalog.publish_book(paper)
        ok("с экземпляром книга опубликована")
        reservation = (await sv.res.reserve(r1, paper)).id
        await sv.session.commit()
        await sv.res.issue(reservation)
        await sv.session.commit()
        await refuse("оценка до возврата книги", sv.rating.rate(r1, paper, 10))
        await sv.res.return_book(reservation)
        await sv.session.commit()
        await sv.rating.rate(r1, paper, 10)
        ok("после возврата экземпляра оценка принята")
        draft = (await sv.catalog.create_book_draft(
            f"Черновик {tag}", "Описание", [lem], [classic])).id
        await sv.copies.register(draft, f"DEMO-{tag}-2")
        await sv.session.commit()
        await sv.catalog.delete_draft(draft)
        ok("черновик удалён вместе с экземпляром")

        print("\n5. Статистика")
        stats = await sv.stats.get_catalog_stats(admin)
        ok(f"книги по статусам: {stats['books_by_status']}")
        await refuse("читатель просит статистику", sv.stats.get_catalog_stats(r1), PermissionError)
    print("\nСценарии блока А выполнены.")


async def _main() -> None:
    try:
        await run_block_a()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())