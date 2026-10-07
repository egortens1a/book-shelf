from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Role, RoleTypes


class RoleRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_name(self, name: RoleTypes | str) -> Role | None:
        result = await self.session.execute(
            select(Role).where(Role.name == RoleTypes(name))
        )
        return result.scalar_one_or_none()