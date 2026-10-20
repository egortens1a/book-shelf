"""Публичные эндпоинты: регистрация и вход."""
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import get_user_service
from app.core.security import create_access_token
from app.schemas.user import TokenRead, UserRead, UserRegister
from app.services.user_service import UserService

router = APIRouter(tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(
    data: UserRegister,
    users: Annotated[UserService, Depends(get_user_service)],
):
    user = await users.register_reader(
        full_name=data.full_name,
        email=data.email,
        password=data.password,
    )
    return UserRead.model_validate(user)


@router.post("/login", response_model=TokenRead)
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    users: Annotated[UserService, Depends(get_user_service)],
):
    user = await users.authenticate(email=form.username, password=form.password)
    token = create_access_token(user_id=user.id, role_id=user.role_id)
    return TokenRead(access_token=token)