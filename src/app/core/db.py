from collections.abc import AsyncIterator
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings

engine = create_async_engine(get_settings().database_url, echo=True, future=True)
session_factory = async_sessionmaker(engine, expire_on_commit=False)

async def get_async_session() -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session
