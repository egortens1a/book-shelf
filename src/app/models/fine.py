import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (BigInteger, DateTime, Enum, ForeignKey, Identity,
                        Numeric, UniqueConstraint, func)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import Base


class FineReason(str, enum.Enum):
    LATE_RETURN = "LATE_RETURN"
    LOST = "LOST"


class FineStatus(str, enum.Enum):
    UNPAID = "UNPAID"
    PAID = "PAID"


class Fine(Base):
    __tablename__ = "fines"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    reservation_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("reservations.id", ondelete="RESTRICT"), index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    reason: Mapped[FineReason] = mapped_column(
        Enum(FineReason, native_enum=False, length=20,
             create_constraint=True, name="fine_reason")
    )
    status: Mapped[FineStatus] = mapped_column(
        Enum(FineStatus, native_enum=False, length=20,
             create_constraint=True, name="fine_status"),
        default=FineStatus.UNPAID,
        server_default=FineStatus.UNPAID.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("reservation_id", "reason", name="uq_fines_reservation_reason"),
    )
