from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.text import normalize_name
from app.models import Author

from app.core.errors import NotFound


class AuthorRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, full_name: str) -> Author:
        author = Author(full_name=normalize_name(full_name))
        self.session.add(author)
        await self.session.flush()
        return author

    async def get_by_id(self, author_id: int) -> Author | None:
        return await self.session.get(Author, author_id)

    async def get_by_full_name(self, full_name: str) -> Author | None:
        return await self.session.scalar(
            select(Author).where(Author.full_name == normalize_name(full_name))
        )

    async def get_all(self) -> list[Author]:
        result = await self.session.execute(select(Author).order_by(Author.full_name))
        return list(result.scalars())

    async def rename(self, author_id: int, new_name: str) -> Author:
        author = await self.get_by_id(author_id)
        if author is None:
            raise NotFound("Автор не найден")
        author.full_name = normalize_name(new_name)
        await self.session.flush()
        return author

    async def delete(self, author_id: int) -> None:
        author = await self.get_by_id(author_id)
        if author is None:
            raise NotFound("Автор не найден")
        await self.session.delete(author)
        await self.session.flush()