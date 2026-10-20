from pydantic import BaseModel, ConfigDict, Field

from app.models import RoleTypes, UserStatus


class UserRegister(BaseModel):
    # Роли здесь нет намеренно: /register всегда создаёт READER.
    full_name: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: str
    role_id: int
    status: UserStatus


class MeRead(UserRead):
    role: RoleTypes | None = None
    genre_ids: list[int] = Field(default_factory=list)


class TokenRead(BaseModel):
    access_token: str
    token_type: str = "bearer"


class InterestsUpdate(BaseModel):
    genre_ids: list[int]


class InterestsRead(BaseModel):
    genre_ids: list[int]