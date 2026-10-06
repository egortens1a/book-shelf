from datetime import datetime
from sqlalchemy import ForeignKey, UniqueConstraint, BigInteger, Identity, func, Text, SmallInteger, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base import Base
from app.models import Book

class WishlistItem(Base):
    __tablename__ = "wishlist_item"
    __table_args__ = (
        UniqueConstraint("user_id", "book_id", name="uq_wishlistitem_user_book"),
    )
    book: Mapped[Book] = relationship("Book", lazy="noload")
    
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete="RESTRICT"))
    book_id: Mapped[int] = mapped_column(ForeignKey('books.id', ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), 
                                                 server_default=func.now())
    
    
class ReadingProgress(Base):
    __tablename__ = "reading_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "book_id", name="uq_readingprogress_user_book"),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete="RESTRICT"))
    book_id: Mapped[int] = mapped_column(ForeignKey('books.id', ondelete="RESTRICT"))
    position: Mapped[int] = mapped_column(BigInteger) # страница, на которой пользователь остановился
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
            

class Rating(Base):
    __tablename__ = "rating"
    __table_args__ = (
        UniqueConstraint("user_id", "book_id", name="uq_rating_user_book"),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete="RESTRICT"))
    book_id: Mapped[int] = mapped_column(ForeignKey('books.id', ondelete="RESTRICT"))
    score: Mapped[int] = mapped_column(SmallInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    