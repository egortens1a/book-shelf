from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AccessType, Book, BookStatus
from app.repositories import AuthorRepository, BookRepository, GenreRepository
from app.services.base import BaseService

# DRAFT -> PUBLISHED -> ARCHIVED
_ALLOWED_TRANSITIONS: dict[BookStatus, set[BookStatus]] = {
    BookStatus.DRAFT: {BookStatus.PUBLISHED},
    BookStatus.PUBLISHED: {BookStatus.ARCHIVED},
    BookStatus.ARCHIVED: set(),
}


class CatalogService(BaseService):
    def __init__(self, session: AsyncSession):
        super().__init__(session)
        self.book_repo = BookRepository(session=session)
        self.genre_repo = GenreRepository(session=session)
        self.author_repo = AuthorRepository(session=session)

    async def _get_book_or_raise(self, book_id: int) -> Book:
        book = await self.book_repo.get_by_id(book_id)
        if book is None:
            raise ValueError("Книга не найдена")
        return book

    @staticmethod
    def _validate_electronic_version(access_type: AccessType, text_content: str | None) -> None:
        if access_type == AccessType.NONE and text_content is not None:
            raise ValueError("При access_type=NONE текст электронной версии должен быть пустым")
        if access_type != AccessType.NONE and not text_content:
            raise ValueError("Для электронной книги (FREE/SUBSCRIPTION) нужен текст")

    async def create_book_draft(
        self,
        title: str,
        description: str,
        author_ids: list[int],
        genre_ids: list[int],
        access_type: AccessType = AccessType.NONE,
        publication_year: int | None = None,
        text_content: str | None = None,
    ) -> Book:
        access_type = AccessType(access_type)
        if not title.strip():
            raise ValueError("Название книги не может быть пустым")
        if not description.strip():
            raise ValueError("Описание книги не может быть пустым")
        self._validate_electronic_version(access_type, text_content)

        author_ids = list(dict.fromkeys(author_ids))  # убрать дубли, сохранив порядок
        genre_ids = list(dict.fromkeys(genre_ids))

        async with self._transaction():
            for author_id in author_ids:
                if await self.author_repo.get_by_id(author_id) is None:
                    raise ValueError(f"Автор {author_id} не найден")
            for genre_id in genre_ids:
                if await self.genre_repo.get_by_id(genre_id) is None:
                    raise ValueError(f"Жанр {genre_id} не найден")

            book = await self.book_repo.create(
                title=title,
                description=description,
                access_type=access_type,
                status=BookStatus.DRAFT,
                publication_year=publication_year,
                text_content=text_content,
            )
            for author_id in author_ids:
                await self.book_repo.add_author(book.id, author_id)
            for genre_id in genre_ids:
                await self.book_repo.add_genre(book.id, genre_id)

        return await self._get_book_or_raise(book.id)

    async def set_electronic_version(
        self, book_id: int, access_type: AccessType, text_content: str | None
    ) -> Book:
        """Загрузка текста электронной версии. После публикации текст не меняется."""
        access_type = AccessType(access_type)
        self._validate_electronic_version(access_type, text_content)

        book = await self._get_book_or_raise(book_id)
        if book.status != BookStatus.DRAFT:
            raise ValueError("Менять электронную версию можно только у черновика")

        async with self._transaction():
            await self.book_repo.set_electronic_version(book_id, access_type, text_content)
        return await self._get_book_or_raise(book_id)

    async def publish_book(self, book_id: int) -> Book:
        book = await self._get_book_or_raise(book_id)
        if book.status != BookStatus.DRAFT:
            raise ValueError("Можно публиковать только черновики")
        if not book.description or not book.description.strip():
            raise ValueError("Книга должна иметь описание")
        if not book.authors:
            raise ValueError("Книга должна иметь хотя бы одного автора")
        if not book.genres:
            raise ValueError("Книга должна иметь хотя бы один жанр")
        
        has_electronic = book.access_type != AccessType.NONE
        if not has_electronic and await self.book_repo.count_active_copies(book_id) == 0:
            raise ValueError(
                "Для публикации нужна электронная версия или хотя бы один бумажный экземпляр"
            )

        return await self._change_status(book_id, BookStatus.PUBLISHED)

    async def archive_book(self, book_id: int) -> Book:
        return await self._change_status(book_id, BookStatus.ARCHIVED)

    async def delete_draft(self, book_id: int) -> None:
        try:
            async with self._transaction():
                await self.book_repo.delete_draft(book_id)
        except IntegrityError as e:  # FK RESTRICT: у книги остались связанные записи
            raise ValueError("Нельзя удалить книгу: есть связанные записи") from e

    async def _change_status(self, book_id: int, target: BookStatus) -> Book:
        book = await self._get_book_or_raise(book_id)
        if target not in _ALLOWED_TRANSITIONS[book.status]:
            raise ValueError(
                f"Недопустимый переход статуса: {book.status.value} -> {target.value}"
            )
        async with self._transaction():
            await self.book_repo.update_status(book_id, target)
        return await self._get_book_or_raise(book_id)

    async def search_books(
        self,
        title: str | None = None,
        author_id: int | None = None,
        genre_id: int | None = None,
        limit: int = 50,
        offset: int = 0,
        include_unpublished: bool = False,
    ) -> list[Book]:
        """Поиск по каталогу. Читателю - только PUBLISHED; include_unpublished для библиотекаря."""
        return await self.book_repo.search(
            title=title.strip() if title else None,
            author_id=author_id,
            genre_id=genre_id,
            status=None if include_unpublished else BookStatus.PUBLISHED,
            limit=max(1, min(limit, 200)),
            offset=max(0, offset),
        )

    async def get_published_book(self, book_id: int) -> Book:
        """Карточка книги для читателя: неопубликованные не показываются."""
        book = await self._get_book_or_raise(book_id)
        if book.status != BookStatus.PUBLISHED:
            raise ValueError("Книга не найдена")
        return book