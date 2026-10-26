from collections.abc import Awaitable, Callable
from typing import TypeVar

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.text import normalize_name
from app.models import Author, Genre, RoleTypes
from app.repositories import AuthorRepository, GenreRepository
from app.services.base import BaseService

from app.core.errors import InvalidInput, Conflict

T = TypeVar("T")


class DirectoryService(BaseService):
    def __init__(self, session: AsyncSession):
        super().__init__(session)
        self.author_repo = AuthorRepository(session)
        self.genre_repo = GenreRepository(session)

    async def _write(self, op: Callable[[], Awaitable[T]], conflict_msg: str) -> T:
        try:
            async with self._transaction():
                return await op()
        except IntegrityError as e:  # UNIQUE или FK RESTRICT
            raise Conflict(conflict_msg) from e

    @staticmethod
    def _clean(name: str, label: str) -> str:
        cleaned = normalize_name(name)
        if not cleaned:
            raise InvalidInput(f"{label} не может быть пустым")
        return cleaned

    # --- авторы ---

    async def list_authors(self) -> list[Author]:
        return await self.author_repo.get_all()

    async def create_author(self, full_name: str) -> Author:
        name = self._clean(full_name, "Имя автора")
        return await self._write(
            lambda: self.author_repo.create(name), "Автор с таким именем уже существует"
        )

    async def rename_author(self, author_id: int, new_name: str) -> Author:
        name = self._clean(new_name, "Имя автора")
        return await self._write(
            lambda: self.author_repo.rename(author_id, name),
            "Автор с таким именем уже существует",
        )

    async def delete_author(self, author_id: int) -> None:
        await self._write(
            lambda: self.author_repo.delete(author_id),
            "Нельзя удалить автора: у него есть книги",
        )

    async def list_genres(self) -> list[Genre]:
        return await self.genre_repo.get_all()

    async def create_genre(self, name: str) -> Genre:
        cleaned = self._clean(name, "Название жанра")
        return await self._write(
            lambda: self.genre_repo.create(cleaned), "Жанр с таким названием уже существует"
        )

    async def rename_genre(self, genre_id: int, new_name: str) -> Genre:
        cleaned = self._clean(new_name, "Название жанра")
        return await self._write(
            lambda: self.genre_repo.rename(genre_id, cleaned),
            "Жанр с таким названием уже существует",
        )

    async def delete_genre(self, genre_id: int) -> None:
        await self._write(
            lambda: self.genre_repo.delete(genre_id),
            "Нельзя удалить жанр: он используется книгами или читателями",
        )