from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.core.errors import InvalidInput

class NameIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)

    @field_validator("name")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise InvalidInput("Имя не может быть пустым")
        return value


class GenreRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class AuthorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str