from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Role, RoleTypes, User, UserStatus


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, full_name: str, email: str, password_hash: str, role_id: int) -> User:
        user = User(full_name=full_name, email=email, password_hash=password_hash, role_id=role_id)
        self.session.add(user)
        await self.session.flush()
        await self.session.refresh(user)
        return user

    async def get_by_id(self, user_id: int) -> User | None:
        result = await self.session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_role_name(self, user_id: int) -> RoleTypes | None:
        result = await self.session.execute(
            select(Role.name).join(User, User.role_id == Role.id).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def set_status(self, user_id: int, status: UserStatus | str) -> User:
        user = await self.get_by_id(user_id)
        if user is None:
            raise ValueError("Пользователь не найден")
        user.status = UserStatus(status)
        await self.session.flush()
        return user

    async def list_users(self, limit: int = 50, offset: int = 0) -> list[User]:
        result = await self.session.execute(
            select(User).order_by(User.id).limit(limit).offset(offset)
        )
        return list(result.scalars().all())