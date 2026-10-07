from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.text import normalize_name
from app.models import Genre


class GenreRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, name: str) -> Genre:
        genre = Genre(name=normalize_name(name))
        self.session.add(genre)
        await self.session.flush()
        return genre

    async def get_by_id(self, genre_id: int) -> Genre | None:
        result = await self.session.execute(
            select(Genre).where(Genre.id == genre_id)
        )
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Genre | None:
        result = await self.session.execute(
            select(Genre).where(Genre.name == normalize_name(name))
        )
        return result.scalar_one_or_none()

    async def get_all(self) -> list[Genre]:
        result = await self.session.execute(select(Genre).order_by(Genre.name))
        return list(result.scalars().all())

    async def rename(self, genre_id: int, new_name: str) -> Genre:
        genre = await self.get_by_id(genre_id)
        if genre is None:
            raise ValueError("Жанр не найден")
        genre.name = normalize_name(new_name)
        await self.session.flush()
        return genre

    async def delete(self, genre_id: int) -> None:
        result = await self.session.execute(delete(Genre).where(Genre.id == genre_id))
        if result.rowcount == 0:
            raise ValueError("Жанр не найден")