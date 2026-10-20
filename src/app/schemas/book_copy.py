from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import CopyStatus


class BookCopyCreate(BaseModel):
    """Постановка экземпляра на учёт. book_id приходит из пути, не из тела."""

    inventory_number: str = Field(min_length=1, max_length=50)


class BookCopyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    book_id: int
    inventory_number: str
    status: CopyStatus
    created_at: datetime
