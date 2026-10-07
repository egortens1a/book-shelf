import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import engine, session_factory
from app.scripts import seed_catalog, seed_loans


async def seed_all(session: AsyncSession) -> None:
    await seed_catalog.ensure_roles(session)

    await seed_catalog.clear_previous(session)
    await seed_catalog.seed(session)

    await seed_loans.clear_previous(session)
    await seed_loans.seed(session)


async def main() -> None:
    async with session_factory() as session:
        await seed_all(session)
        await session.commit()
        print("Общие тестовые данные загружены. В базе сейчас:")
        await seed_loans.report(session)    # пользователи, книги, экземпляры, подписки, брони, штрафы
        await seed_catalog.report(session)  # жанры, авторы, оценки, прогресс, списки
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())