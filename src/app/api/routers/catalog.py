from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import (
    get_book_copy_service,
    get_catalog_service,
    get_current_user,
    get_rating_service,
    require_role,
)
from app.models import RoleTypes
from app.schemas.catalog import (
    BookDetailRead,
    BookDraftCreate,
    BookRead,
    BookUpdate,
    ElectronicVersionUpdate,
    RatingSummaryRead,
)
from app.services.book_copy_service import BookCopyService
from app.services.catalog_service import CatalogService
from app.services.rating_service import RatingService

reader_router = APIRouter(
    prefix="",
    tags=["catalog"],
    dependencies=[Depends(get_current_user)],
)

librarian_router = APIRouter(
    prefix="/librarian/books",
    tags=["librarian"],
    dependencies=[Depends(require_role(RoleTypes.LIBRARIAN))],
)

_Catalog = Annotated[CatalogService, Depends(get_catalog_service)]


# ---------------- публичный каталог ----------------

@reader_router.get("/books", response_model=list[BookRead])
async def search_books(
    service: _Catalog,
    title: str | None = None,
    author_id: int | None = None,
    genre_id: int | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    return await service.search_books(
        title=title, author_id=author_id, genre_id=genre_id,
        limit=limit, offset=offset,
    )


@reader_router.get("/books/{book_id}", response_model=BookDetailRead)
async def get_book_card(
    book_id: int,
    catalog: _Catalog,
    copies: Annotated[BookCopyService, Depends(get_book_copy_service)],
    ratings: Annotated[RatingService, Depends(get_rating_service)],
):
    book = await catalog.get_published_book(book_id)
    summary = await ratings.get_book_summary(book_id)
    available = await copies.count_available(book_id)

    # ORM -> DTO. text_content не трогаем: он defer'd.
    card = BookDetailRead.model_validate(book)
    card.copies_available = available or 0
    card.rating = RatingSummaryRead(count=summary.count, average=summary.average)
    return card


# ---------------- библиотекарь ----------------

@librarian_router.get("", response_model=list[BookRead])
async def librarian_search(
    service: _Catalog,
    title: str | None = None,
    author_id: int | None = None,
    genre_id: int | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    return await service.search_books(
        title=title, author_id=author_id, genre_id=genre_id,
        limit=limit, offset=offset, include_unpublished=True,
    )


@librarian_router.get("/{book_id}", response_model=BookRead)
async def librarian_get_book(book_id: int, service: _Catalog):
    return await service.get_book_any_status(book_id)


@librarian_router.post("", response_model=BookRead, status_code=status.HTTP_201_CREATED)
async def create_draft(data: BookDraftCreate, service: _Catalog):
    return await service.create_book_draft(
        title=data.title,
        description=data.description or "",
        publication_year=data.publication_year,
        author_ids=data.author_ids,
        genre_ids=data.genre_ids,
    )


@librarian_router.patch("/{book_id}", response_model=BookRead)
async def update_book(data: BookUpdate, book_id: int, service: _Catalog):
    return await service.update_book(
        book_id,
        title=data.title,
        description=data.description,
        publication_year=data.publication_year,
        author_ids=data.author_ids,
        genre_ids=data.genre_ids,
    )


@librarian_router.put("/{book_id}/electronic", response_model=BookRead)
async def set_electronic(book_id: int, data: ElectronicVersionUpdate, service: _Catalog):
    return await service.set_electronic_version(
        book_id, access_type=data.access_type, text_content=data.text_content
    )


@librarian_router.post("/{book_id}/publish", response_model=BookRead)
async def publish_book(book_id: int, service: _Catalog):
    return await service.publish_book(book_id)


@librarian_router.post("/{book_id}/archive", response_model=BookRead)
async def archive_book(book_id: int, service: _Catalog):
    return await service.archive_book(book_id)


@librarian_router.delete("/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_draft(book_id: int, service: _Catalog):
    await service.delete_draft(book_id)