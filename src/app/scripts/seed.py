import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import engine, session_factory
from app.models import User  # импорт app.models регистрирует в metadata все таблицы
from app.scripts import seed_catalog, seed_loans, seed_api


async def wipe_database(session: AsyncSession) -> None:
    preparer = session.sync_session.get_bind().dialect.identifier_preparer
    tables = ", ".join(preparer.format_table(t) for t in User.metadata.sorted_tables)
    await session.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))


async def seed_all(session: AsyncSession) -> None:
    await wipe_database(session)
    await seed_catalog.ensure_roles(session)
    await seed_catalog.seed(session)
    await seed_loans.seed(session)
    # lab2
    await seed_api.ensure_seed(session)
    await session.commit()


async def main() -> None:
    async with session_factory() as session:
        await seed_all(session)
        await session.commit()
        print("База очищена, общие тестовые данные загружены. В базе сейчас:")
        await seed_loans.report(session)    # пользователи, книги, экземпляры, подписки, брони, штрафы
        await seed_catalog.report(session)  # жанры, авторы, оценки, прогресс, списки
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())