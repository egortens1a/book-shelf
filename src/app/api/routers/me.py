"""Эндпоинты текущего пользователя. user_id всегда берётся из токена."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user, get_user_service, require_role
from app.models import RoleTypes, User
from app.schemas.user import InterestsRead, InterestsUpdate, MeRead
from app.services.user_service import UserService

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=MeRead)
async def get_me(
    user: Annotated[User, Depends(get_current_user)],
    users: Annotated[UserService, Depends(get_user_service)],
):
    genre_ids = await users.get_interest_ids(user.id)
    role = await users.user_repo.get_role_name(user.id)
    return MeRead.model_validate(user).model_copy(
        update={"genre_ids": genre_ids, "role": role}
    )


@router.get("/interests", response_model=InterestsRead)
async def get_interests(
    user: Annotated[User, Depends(require_role(RoleTypes.READER))],
    users: Annotated[UserService, Depends(get_user_service)],
):
    return InterestsRead(genre_ids=await users.get_interest_ids(user.id))


@router.put("/interests", response_model=InterestsRead)
async def put_interests(
    data: InterestsUpdate,
    user: Annotated[User, Depends(require_role(RoleTypes.READER))],
    users: Annotated[UserService, Depends(get_user_service)],
):
    genre_ids = await users.set_interests(user.id, data.genre_ids)
    return InterestsRead(genre_ids=genre_ids)