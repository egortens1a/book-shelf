import enum
from sqlalchemy import BigInteger, SmallInteger, Identity, String, Enum, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.base import Base
from datetime import datetime

class UserStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"

class User(Base):
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role_id: Mapped[int] = mapped_column(
            SmallInteger, ForeignKey("roles.id", ondelete="RESTRICT"), index=True
        )
    status: Mapped[UserStatus] = mapped_column(Enum(UserStatus, native_enum=False, length=20,
                                                    create_constraint=True, name="user_status"),
                                               default=UserStatus.ACTIVE,
                                               server_default=UserStatus.ACTIVE.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    