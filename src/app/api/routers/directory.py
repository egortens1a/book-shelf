"""Справочники жанров и авторов

router       - чтение для любой роли (нужен действующий токен);
router_admin - изменение, только ADMIN.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import get_current_user, get_directory_service, require_role
from app.models import RoleTypes
from app.schemas.directory import AuthorRead, GenreRead, NameIn
from app.services.directory_service import DirectoryService

router = APIRouter(
    tags=["directory"],
    dependencies=[Depends(get_current_user)],
)

router_admin = APIRouter(
    tags=["admin: directory"],
    dependencies=[Depends(require_role(RoleTypes.ADMIN))],
)

Directory = Annotated[DirectoryService, Depends(get_directory_service)]


# ---------- чтение (все роли) ----------

@router.get("/genres", response_model=list[GenreRead])
async def list_genres(service: Directory):
    return await service.list_genres()


@router.get("/authors", response_model=list[AuthorRead])
async def list_authors(service: Directory):
    return await service.list_authors()


# ---------- изменение (ADMIN): жанры ----------

@router_admin.post("/genres", response_model=GenreRead, status_code=status.HTTP_201_CREATED)
async def create_genre(service: Directory, data: NameIn):
    return await service.create_genre(data.name)


@router_admin.patch("/genres/{genre_id}", response_model=GenreRead)
async def rename_genre(genre_id: int, service: Directory, data: NameIn):
    return await service.rename_genre(genre_id, data.name)


@router_admin.delete("/genres/{genre_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_genre(genre_id: int, service: Directory):
    await service.delete_genre(genre_id)


# ---------- изменение (ADMIN): авторы ----------

@router_admin.post("/authors", response_model=AuthorRead, status_code=status.HTTP_201_CREATED)
async def create_author(service: Directory, data: NameIn):
    return await service.create_author(data.name)


@router_admin.patch("/authors/{author_id}", response_model=AuthorRead)
async def rename_author(author_id: int, service: Directory, data: NameIn):
    return await service.rename_author(author_id, data.name)


@router_admin.delete("/authors/{author_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_author(author_id: int, service: Directory):
    await service.delete_author(author_id)