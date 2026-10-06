import enum
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Identity, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import Base


class CopyStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    RESERVED = "RESERVED"
    ISSUED = "ISSUED"
    LOST = "LOST"
    WRITTEN_OFF = "WRITTEN_OFF"


class BookCopy(Base):
    __tablename__ = "book_copies"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    book_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("books.id", ondelete="RESTRICT"), index=True
    )
    inventory_number: Mapped[str] = mapped_column(String(50), unique=True)
    status: Mapped[CopyStatus] = mapped_column(
        Enum(CopyStatus, native_enum=False, length=20,
             create_constraint=True, name="copy_status"),
        default=CopyStatus.AVAILABLE,
        server_default=CopyStatus.AVAILABLE.value,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
