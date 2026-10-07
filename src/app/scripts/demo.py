"""Единый прогон демонстрации: общий seed, сценарии блока А, сценарии блока Б.

Блок А (demo_catalog) создаёт свои данные с уникальной меткой и не сбрасывает базу.
Блок Б (demo_loans) перед прогоном приводит свои данные к состоянию seed_loans.
Стык блоков проверяется в demo_catalog: подписка из блока Б открывает подписные
книги, возврат бумажного экземпляра открывает оценку, экземпляр позволяет
опубликовать бумажную книгу.

Запуск (из каталога src):  python -m app.scripts.demo
"""

import asyncio

from app.core.db import engine, session_factory
from app.scripts import demo_catalog, demo_loans
from app.scripts.seed import seed_all

engine.echo = False


def banner(text: str) -> None:
    print(f"\n{'#' * 70}\n# {text}\n{'#' * 70}")


async def main() -> None:
    banner("ОБЩИЕ ТЕСТОВЫЕ ДАННЫЕ")
    async with session_factory() as session:
        await seed_all(session)
        await session.commit()
    print("Данные добавлены")

    banner("БЛОК А: пользователи, каталог, чтение, оценки")
    await demo_catalog.run_block_a(session_factory)

    banner("БЛОК Б: подписки, бронирование, выдача, штрафы")
    await demo_loans.main()

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())