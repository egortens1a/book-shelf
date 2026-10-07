import asyncio

import app.models
from app.core.base import Base
from app.core.db import engine


async def create_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def main() -> None:
    await create_tables()
    await drop_tables() # закомментировать для теста, тк потому это будет делать Alembic
    await engine.dispose()


asyncio.run(main())