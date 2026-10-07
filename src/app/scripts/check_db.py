import asyncio
from sqlalchemy import text
from app.core.db import engine


async def check_database_connection() -> bool:
    async with engine.connect() as connection:
        try:
            postgres_version = await connection.execute(text("SELECT version()"))
            print(f"\nPostgreSQL version: {postgres_version.scalar()}")
            return True
        except Exception:
            return False
        
asyncio.run(check_database_connection())