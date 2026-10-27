from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RoleTypes, UserStatus
from app.repositories import UserRepository

from app.core.errors import Forbidden, UserNotFound

class BaseService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)

    @asynccontextmanager
    async def _transaction(self) -> AsyncGenerator[None, None]:
        async with self.session.begin_nested():
            yield

    async def _require_role(self, user_id: int, *roles: RoleTypes) -> None:
        """Пользователь существует, не заблокирован и имеет одну из ролей.

        Ошибки берутся из доменной иерархии: встроенный PermissionError
        не покрыт обработчиками в error_handlers и дал бы 500 вместо 403.
        """
        user = await self.user_repo.get_by_id(user_id)
        if user is None:
            raise UserNotFound("Пользователь не найден")
        if user.status != UserStatus.ACTIVE:
            raise Forbidden("Пользователь заблокирован")
        if await self.user_repo.get_role_name(user_id) not in roles:
            raise Forbidden("Недостаточно прав")