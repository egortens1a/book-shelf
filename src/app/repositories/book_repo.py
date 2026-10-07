from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    AccessType, Book, BookAuthor, BookCopy, BookGenre, BookStatus, CopyStatus,
)


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
        result = await self.session.execute(
            select(Book)
            .options(selectinload(Book.authors), selectinload(Book.genres))
            .where(Book.id == book_id)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def get_text_content(self, book_id: int) -> str | None:
        result = await self.session.execute(
            select(Book.text_content).where(Book.id == book_id)
        )
        return result.scalar_one_or_none()

    async def set_electronic_version(
        self, book_id: int, access_type: AccessType | str, text_content: str | None
    ) -> Book:
        """Меняет access_type и text_content одним UPDATE, чтобы CHECK не сработал между ними."""
        book = await self.get_by_id(book_id)
        if book is None:
            raise ValueError("Книга не найдена")
        book.access_type = AccessType(access_type)
        book.text_content = text_content
        await self.session.flush()
        return book

    async def add_author(self, book_id: int, author_id: int) -> None:
        # Дубликат отсекает UNIQUE в БД, поэтому гонки между проверкой и вставкой нет.
        stmt = (
            pg_insert(BookAuthor)
            .values(book_id=book_id, author_id=author_id)
            .on_conflict_do_nothing(index_elements=[BookAuthor.book_id, BookAuthor.author_id])
        )
        await self.session.execute(stmt)

    async def add_genre(self, book_id: int, genre_id: int) -> None:
        stmt = (
            pg_insert(BookGenre)
            .values(book_id=book_id, genre_id=genre_id)
            .on_conflict_do_nothing(index_elements=[BookGenre.book_id, BookGenre.genre_id])
        )
        await self.session.execute(stmt)

    async def search(
        self,
        title: str | None = None,
        author_id: int | None = None,
        genre_id: int | None = None,
        status: BookStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Book]:
        query = select(Book).options(selectinload(Book.authors), selectinload(Book.genres))
        if title:
            query = query.where(Book.title.icontains(title, autoescape=True))
        if author_id is not None:
            query = query.where(
                Book.id.in_(select(BookAuthor.book_id).where(BookAuthor.author_id == author_id))
            )
        if genre_id is not None:
            query = query.where(
                Book.id.in_(select(BookGenre.book_id).where(BookGenre.genre_id == genre_id))
            )
        if status is not None:
            query = query.where(Book.status == status)
        query = query.order_by(Book.id).limit(limit).offset(offset)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update_status(self, book_id: int, status: BookStatus | str) -> Book:
        book = await self.get_by_id(book_id)
        if book is None:
            raise ValueError("Книга не найдена")
        book.status = BookStatus(status)
        await self.session.flush()
        return book

    async def delete_draft(self, book_id: int) -> None:
        book = await self.get_by_id(book_id)
        if book is None:
            raise ValueError("Книга не найдена")
        if book.status != BookStatus.DRAFT:
            raise ValueError("Удалять можно только черновики")
        
        await self.session.execute(delete(BookCopy).where(BookCopy.book_id == book_id))
        await self.session.delete(book)
        await self.session.flush()

    async def get_text_length(self, book_id: int) -> int | None:
        """Длина текста в символах, без загрузки самого текста"""
        result = await self.session.execute(
            select(func.length(Book.text_content)).where(Book.id == book_id)
        )
        return result.scalar_one_or_none()

    async def count_active_copies(self, book_id: int) -> int:
        """Бумажные экземпляры в обороте: без утерянных и списанных"""
        result = await self.session.execute(
            select(func.count())
            .select_from(BookCopy)
            .where(
                BookCopy.book_id == book_id,
                BookCopy.status.not_in([CopyStatus.LOST, CopyStatus.WRITTEN_OFF]),
            )
        )
        return result.scalar_one()