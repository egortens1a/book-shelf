from sqlalchemy import String, BigInteger, Identity
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.base import Base

class Genre(Base):
    __tablename__ = "genres"
    books = relationship("Book", secondary="book_genre", back_populates="genres")
        
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    