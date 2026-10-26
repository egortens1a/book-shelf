from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.models import AccessType, BookStatus
from app.schemas.directory import AuthorRead, GenreRead


class BookRead(BaseModel):
    """Список/черновик"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None = None
    publication_year: int | None = None
    status: BookStatus
    access_type: AccessType
    authors: list[AuthorRead] = Field(default_factory=list)
    genres: list[GenreRead] = Field(default_factory=list)


class RatingSummaryRead(BaseModel):
    count: int = 0
    average: float | None = None


class BookDetailRead(BookRead):
    copies_available: int = 0
    rating: RatingSummaryRead = Field(default_factory=RatingSummaryRead)

    @computed_field
    @property
    def available_online(self) -> bool:
        return self.access_type != AccessType.NONE


class BookDraftCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    publication_year: int | None = Field(default=None, ge=1, le=9999)
    author_ids: list[int] = Field(default_factory=list)
    genre_ids: list[int] = Field(default_factory=list)


class BookUpdate(BaseModel):
    """None = не менять. Текста электронной версии здесь нет намеренно."""

    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    publication_year: int | None = Field(default=None, ge=1, le=9999)
    author_ids: list[int] | None = None
    genre_ids: list[int] | None = None


class ElectronicVersionUpdate(BaseModel):
    access_type: AccessType
    text_content: str | None = None