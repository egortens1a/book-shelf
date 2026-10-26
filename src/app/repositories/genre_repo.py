from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.text import normalize_name
from app.models import Genre

from app.core.errors import GenreNotFound


class GenreRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, name: str) -> Genre:
        genre = Genre(name=normalize_name(name))
        self.session.add(genre)
        await self.session.flush()
        return genre

    async def get_by_id(self, genre_id: int) -> Genre | None:
        return await self.session.get(Genre, genre_id)

    async def get_by_name(self, name: str) -> Genre | None:
        return await self.session.scalar(
            select(Genre).where(Genre.name == normalize_name(name))
        )

    async def get_all(self) -> list[Genre]:
        result = await self.session.scalars(select(Genre).order_by(Genre.name))
        return list(result.all())

    async def rename(self, genre_id: int, new_name: str) -> Genre:
        genre = await self.get_by_id(genre_id)
        if genre is None:
            raise GenreNotFound("Жанр не найден")
        genre.name = normalize_name(new_name)
        await self.session.flush()
        return genre

    async def delete(self, genre_id: int) -> None:
        genre = await self.get_by_id(genre_id)
        if genre is None:
            raise GenreNotFound("Жанр не найден")
        await self.session.delete(genre)
        await self.session.flush()