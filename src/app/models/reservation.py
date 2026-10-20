import enum
from datetime import datetime

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Identity, Index, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base import Base, enum_check

if TYPE_CHECKING:
    from app.models.book_copy import BookCopy


class ReservationStatus(str, enum.Enum):
    CREATED = "CREATED"
    ISSUED = "ISSUED"
    RETURNED = "RETURNED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    LOST = "LOST"


class Reservation(Base):
    __tablename__ = "reservations"
    __table_args__ = (
        enum_check("status", ReservationStatus, "reservation_status"),
        Index(
            "uq_reservations_copy_active",
            "copy_id",
            unique=True,
            postgresql_where=text("status IN ('CREATED', 'ISSUED')"),
        ),
    )

    # Связь только в одну сторону: от брони к экземпляру. Обратная сторона
    # не нужна, поэтому back_populates не задаём. lazy="raise" запрещает
    # ленивую подгрузку: без явного selectinload обращение к copy даст
    # понятную ошибку, а не MissingGreenlet из глубины сериализатора.
    copy: Mapped["BookCopy"] = relationship(lazy="raise")

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    copy_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("book_copies.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[ReservationStatus] = mapped_column(
        Enum(ReservationStatus, native_enum=False, length=20, create_constraint=False),
        default=ReservationStatus.CREATED,
        server_default=ReservationStatus.CREATED.value,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    pickup_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
