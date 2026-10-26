from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ReadingContentRead(BaseModel):
    """Текст книги и позиция, с которой читатель продолжит.

    Отдаётся только по GET /books/{id}/read: в списки и карточки
    text_content не попадает.
    """

    text: str
    position: int


class ProgressRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    book_id: int
    position: int
    finished_at: datetime | None = None
    updated_at: datetime


class ProgressUpdate(BaseModel):
    position: int = Field(ge=0)
