"""Эндпоинты текущего пользователя. user_id всегда берётся из токена."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user, get_user_service, require_role
from app.models import RoleTypes, User
from app.schemas.recommendation import RecommendationsRead
from app.schemas.user import InterestsRead, InterestsUpdate, MeRead
from app.services.user_service import UserService

router = APIRouter(prefix="/me", tags=["me"])

Users = Annotated[UserService, Depends(get_user_service)]
Reader = Annotated[User, Depends(require_role(RoleTypes.READER))]


@router.get("", response_model=MeRead)
async def get_me(
    user: Annotated[User, Depends(get_current_user)],
    users: Users,
):
    genre_ids = await users.get_interest_ids(user.id)
    role = await users.user_repo.get_role_name(user.id)
    return MeRead.model_validate(user).model_copy(
        update={"genre_ids": genre_ids, "role": role}
    )


@router.get("/interests", response_model=InterestsRead)
async def get_interests(user: Reader, users: Users):
    return InterestsRead(genre_ids=await users.get_interest_ids(user.id))


@router.put("/interests", response_model=InterestsRead)
async def put_interests(data: InterestsUpdate, user: Reader, users: Users):
    genre_ids = await users.set_interests(user.id, data.genre_ids)
    return InterestsRead(genre_ids=genre_ids)


@router.get("/recommendations", response_model=RecommendationsRead)
async def get_recommendations(user: Reader):
    # Заглушка ЛР2: всегда пустой список. В ЛР3 здесь появится вызов gRPC.
    return RecommendationsRead(items=[])