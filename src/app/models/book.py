import enum
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, Identity, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import Base, enum_check

class BookStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"
    
class AccessType(str, enum.Enum):
    FREE = "FREE"
    SUBSCRIPTION = "SUBSCRIPTION"
    NONE = "NONE"
    
class Book(Base):
    __tablename__ = "books"
    __table_args__ = (
        enum_check("access_type", AccessType, "access_type"),
        enum_check("status", BookStatus, "book_status")
        )
    
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    publication_year: Mapped[int | None] = mapped_column(Integer)
    access_type: Mapped[AccessType] = mapped_column(
        Enum(AccessType, native_enum=False, length=20, create_constraint=False),
        default=AccessType.NONE, server_default=AccessType.NONE.value
    )
    status: Mapped[BookStatus] = mapped_column(
        Enum(BookStatus, native_enum=False, length=20, create_constraint=False),
        default=BookStatus.DRAFT, server_default=BookStatus.DRAFT.value
    )
    text_content: Mapped[str | None] = mapped_column(Text, 
                                                     default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), 
                                                 server_default=func.now())