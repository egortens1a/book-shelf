from sqlalchemy import String, BigInteger, Identity
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.base import Base 

class Author(Base):
    __tablename__ = "authors"
    books = relationship("Book", secondary="book_author", back_populates="authors")
    
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    