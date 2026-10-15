from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    AccessType,
    Author,
    Book,
    BookCopy,
    BookStatus,
    CopyStatus,
    Genre,
    Rating,
)

_BOOK_LOAD_OPTIONS = (selectinload(Book.authors), selectinload(Book.genres))


class BookRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        title: str,
        description: str,
        access_type: AccessType | str = AccessType.NONE,
        status: BookStatus | str = BookStatus.DRAFT,
        publication_year: int | None = None,
        text_content: str | None = None,
    ) -> Book:
        book = Book(
            title=title.strip(),
            description=description.strip(),
            publication_year=publication_year,
            access_type=AccessType(access_type),
            status=BookStatus(status),
            text_content=text_content,
        )
        self.session.add(book)
        await self.session.flush()
        await self.session.refresh(book)
        return book

    async def get_by_id(self, book_id: int) -> Book | None:
        return await self.session.get(
            Book, book_id, options=_BOOK_LOAD_OPTIONS, populate_existing=True
        )

    async def _get_or_raise(self, book_id: int) -> Book:
        book = await self.get_by_id(book_id)
        if book is None:
            raise ValueError("Книга не найдена")
        return book

    async def get_most_popular(self) -> Book | None:
        """Книга с наивысшей средней оценкой; считается в БД, а не в Python.

        При равенстве выигрывает та, у которой больше оценок. Книги без
        оценок не участвуют (раньше это приводило к делению на ноль).
        """
        return await self.session.scalar(
            select(Book)
            .join(Rating, Rating.book_id == Book.id)
            .options(*_BOOK_LOAD_OPTIONS, selectinload(Book.ratings))
            .group_by(Book.id)
            .order_by(
                func.avg(Rating.score).desc(),
                func.count(Rating.id).desc(),
                Book.id,
            )
            .limit(1)
        )

    async def get_text_content(self, book_id: int) -> str | None:
        return await self.session.scalar(
            select(Book.text_content).where(Book.id == book_id)
        )

    async def get_text_length(self, book_id: int) -> int | None:
        """Длина текста в символах, без загрузки самого текста."""
        return await self.session.scalar(
            select(func.length(Book.text_content)).where(Book.id == book_id)
        )

    async def set_electronic_version(
        self, book_id: int, access_type: AccessType | str, text_content: str | None
    ) -> Book:
        """Меняет access_type и text_content одним UPDATE, чтобы CHECK не сработал между ними."""
        book = await self._get_or_raise(book_id)
        book.access_type = AccessType(access_type)
        book.text_content = text_content
        await self.session.flush()
        return book

    async def add_author(self, book_id: int, author_id: int) -> None:
        book = await self._get_or_raise(book_id)
        author = await self.session.get(Author, author_id)
        if author is None:
            raise ValueError("Автор не найден")
        if author not in book.authors:
            book.authors.append(author)
            await self.session.flush()

    async def add_genre(self, book_id: int, genre_id: int) -> None:
        book = await self._get_or_raise(book_id)
        genre = await self.session.get(Genre, genre_id)
        if genre is None:
            raise ValueError("Жанр не найден")
        if genre not in book.genres:
            book.genres.append(genre)
            await self.session.flush()

    async def search(
        self,
        title: str | None = None,
        author_id: int | None = None,
        genre_id: int | None = None,
        status: BookStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Book]:
        query = select(Book).options(*_BOOK_LOAD_OPTIONS)
        if title:
            query = query.where(Book.title.icontains(title, autoescape=True))
        if author_id is not None:
            query = query.where(Book.authors.any(Author.id == author_id))
        if genre_id is not None:
            query = query.where(Book.genres.any(Genre.id == genre_id))
        if status is not None:
            query = query.where(Book.status == status)

        result = await self.session.scalars(
            query.order_by(Book.id).limit(limit).offset(offset)
        )
        return list(result.all())

    async def update_status(self, book_id: int, status: BookStatus | str) -> Book:
        book = await self._get_or_raise(book_id)
        book.status = BookStatus(status)
        await self.session.flush()
        return book

    async def delete_draft(self, book_id: int) -> None:
        book = await self._get_or_raise(book_id)
        if book.status != BookStatus.DRAFT:
            raise ValueError("Удалять можно только черновики")

        await self.session.execute(delete(BookCopy).where(BookCopy.book_id == book_id))
        await self.session.delete(book)
        await self.session.flush()

    async def count_active_copies(self, book_id: int) -> int | None:
        """Бумажные экземпляры в обороте: без утерянных и списанных."""
        return await self.session.scalar(
            select(func.count(BookCopy.id)).where(
                BookCopy.book_id == book_id,
                BookCopy.status.not_in([CopyStatus.LOST, CopyStatus.WRITTEN_OFF]),
            )
        )