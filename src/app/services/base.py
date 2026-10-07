from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RoleTypes, UserStatus
from app.repositories import UserRepository


class BaseService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)

    @asynccontextmanager
    async def _transaction(self) -> AsyncGenerator[None, None]:
        try:
            yield
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

    async def _require_role(self, user_id: int, *roles: RoleTypes) -> None:
        """Пользователь существует, не заблокирован и имеет одну из ролей"""
        user = await self.user_repo.get_by_id(user_id)
        if user is None:
            raise ValueError("Пользователь не найден")
        if user.status != UserStatus.ACTIVE:
            raise PermissionError("Пользователь заблокирован")
        if await self.user_repo.get_role_name(user_id) not in roles:
            raise PermissionError("Недостаточно прав")