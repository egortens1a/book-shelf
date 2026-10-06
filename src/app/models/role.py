import enum
from sqlalchemy import SmallInteger, Identity, Enum
from sqlalchemy.orm import Mapped, mapped_column
from app.core.base import Base, enum_check

class RoleTypes(str, enum.Enum):
    READER = "READER"
    LIBRARIAN = "LIBRARIAN"
    ADMIN = "ADMIN"
    
class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (
        enum_check("name", RoleTypes, "role_type"),
    )
    
    id: Mapped[int] = mapped_column(SmallInteger, Identity(), primary_key=True)
    name: Mapped[RoleTypes] = mapped_column(Enum(RoleTypes, native_enum=False, length=20, create_constraint=False), 
                                            unique=True)