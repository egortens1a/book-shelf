from sqlalchemy import ForeignKey, UniqueConstraint, BigInteger, Identity
from sqlalchemy.orm import Mapped, mapped_column
from app.core.base import Base

class UserGenre(Base):
    __tablename__ = "user_genre"
    __table_args__ = (
        UniqueConstraint("user_id", "genre_id", name="uq_assoc_user_genre"),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete="RESTRICT"))
    genre_id: Mapped[int] = mapped_column(ForeignKey('genres.id', ondelete="RESTRICT"))

class BookGenre(Base):
    __tablename__ = "book_genre"
    __table_args__ = (
        UniqueConstraint("book_id", "genre_id", name="uq_assoc_book_genre"),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey('books.id', ondelete="RESTRICT"))
    genre_id: Mapped[int] = mapped_column(ForeignKey('genres.id', ondelete="RESTRICT"))

class BookAuthor(Base):
    __tablename__ = "book_author"
    __table_args__ = (
        UniqueConstraint("book_id", "author_id", name="uq_assoc_book_author"),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey('books.id', ondelete="RESTRICT"))
    author_id: Mapped[int] = mapped_column(ForeignKey('authors.id', ondelete="RESTRICT"))