"""Администрирование пользователей: список, библиотекари, блокировка."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_user_service, require_role
from app.models import RoleTypes
from app.schemas.user import UserRead, UserRegister
from app.services.user_service import UserService

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_role(RoleTypes.ADMIN))],
)

Users = Annotated[UserService, Depends(get_user_service)]


@router.get("/users", response_model=list[UserRead])
async def list_users(
    service: Users,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    return await service.list_users(limit=limit, offset=offset)


@router.post("/librarians", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_librarian(data: UserRegister, service: Users):
    librarian = await service.create_librarian(
        full_name=data.full_name,
        email=data.email,
        password=data.password,
    )
    return UserRead.model_validate(librarian)


@router.post("/users/{user_id}/block", response_model=UserRead)
async def block_user(user_id: int, service: Users):
    return await service.block_user(user_id=user_id)


@router.post("/users/{user_id}/unblock", response_model=UserRead)
async def unblock_user(user_id: int, service: Users):
    return await service.unblock_user(user_id=user_id)