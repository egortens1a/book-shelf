from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RatingIn(BaseModel):
    score: int = Field(ge=1, le=10)
    comment: str | None = Field(default=None, max_length=1000)

    @field_validator("comment")
    @classmethod
    def _blank_to_none(cls, value: str | None) -> str | None:
        # Пустой или состоящий из пробелов комментарий храним как отсутствующий.
        return (value or "").strip() or None


class RatingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    book_id: int
    score: int
    comment: str | None = None
    created_at: datetime