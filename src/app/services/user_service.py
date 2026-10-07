import re

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    MAX_PASSWORD_BYTES, MIN_PASSWORD_LENGTH, hash_password, verify_password,
)
from app.core.text import collapse_spaces, normalize_email
from app.models import RoleTypes, User, UserStatus
from app.repositories import GenreRepository, RoleRepository, UserGenreRepository
from app.services.base import BaseService

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_EMAIL_TAKEN = "Пользователь с таким email уже зарегистрирован"


class UserService(BaseService):
    def __init__(self, session: AsyncSession):
        super().__init__(session)
        self.role_repo = RoleRepository(session)
        self.genre_repo = GenreRepository(session)
        self.user_genre_repo = UserGenreRepository(session)


    async def register_reader(
        self, full_name: str, email: str, password: str, genre_ids: list[int] | None = None
    ) -> User:
        return await self._create_user(RoleTypes.READER, full_name, email, password, genre_ids or [])

    async def create_librarian(self, actor_id: int, full_name: str, email: str, password: str) -> User:
        await self._require_role(actor_id, RoleTypes.ADMIN)
        return await self._create_user(RoleTypes.LIBRARIAN, full_name, email, password, [])

    async def authenticate(self, email: str, password: str) -> User:
        user = await self.user_repo.get_by_email(normalize_email(email))
        if user is None or not verify_password(password, user.password_hash):
            raise ValueError("Неверный email или пароль")
        if user.status == UserStatus.BLOCKED:
            raise PermissionError("Пользователь заблокирован")
        return user

    async def _create_user(
        self, role: RoleTypes, full_name: str, email: str, password: str, genre_ids: list[int]
    ) -> User:
        full_name = collapse_spaces(full_name)
        email = normalize_email(email)
        if not full_name:
            raise ValueError("Имя не может быть пустым")
        if not _EMAIL_RE.match(email):
            raise ValueError("Некорректный email")
        if len(password) < MIN_PASSWORD_LENGTH:
            raise ValueError(f"Пароль должен быть не короче {MIN_PASSWORD_LENGTH} символов")
        if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
            raise ValueError(f"Пароль не должен быть длиннее {MAX_PASSWORD_BYTES} байт")

        genre_ids = await self._validated_genre_ids(genre_ids)
        role_row = await self.role_repo.get_by_name(role)
        if role_row is None:
            raise ValueError(f"Роль {role.value} не найдена: заполните справочник ролей")

        try:
            async with self._transaction():
                if await self.user_repo.get_by_email(email) is not None:
                    raise ValueError(_EMAIL_TAKEN)
                user = await self.user_repo.create(
                    full_name=full_name,
                    email=email,
                    password_hash=hash_password(password),
                    role_id=role_row.id,
                )
                await self.user_genre_repo.replace(user.id, genre_ids)
        except IntegrityError as e:
            raise ValueError(_EMAIL_TAKEN) from e
        return user


    async def set_interests(self, user_id: int, genre_ids: list[int]) -> list[int]:
        if await self.user_repo.get_by_id(user_id) is None:
            raise ValueError("Пользователь не найден")
        genre_ids = await self._validated_genre_ids(genre_ids)
        async with self._transaction():
            await self.user_genre_repo.replace(user_id, genre_ids)
        return genre_ids

    async def get_interest_ids(self, user_id: int) -> list[int]:
        return await self.user_genre_repo.get_genre_ids(user_id)

    async def _validated_genre_ids(self, genre_ids: list[int]) -> list[int]:
        unique = list(dict.fromkeys(genre_ids))
        for genre_id in unique:
            if await self.genre_repo.get_by_id(genre_id) is None:
                raise ValueError(f"Жанр {genre_id} не найден")
        return unique


    async def block_user(self, actor_id: int, user_id: int) -> User:
        return await self._set_reader_status(actor_id, user_id, UserStatus.BLOCKED)

    async def unblock_user(self, actor_id: int, user_id: int) -> User:
        return await self._set_reader_status(actor_id, user_id, UserStatus.ACTIVE)

    async def list_users(self, actor_id: int, limit: int = 50, offset: int = 0) -> list[User]:
        await self._require_role(actor_id, RoleTypes.ADMIN)
        return await self.user_repo.list_users(max(1, min(limit, 200)), max(0, offset))

    async def _set_reader_status(self, actor_id: int, user_id: int, status: UserStatus) -> User:
        await self._require_role(actor_id, RoleTypes.ADMIN)
        target_role = await self.user_repo.get_role_name(user_id)
        if target_role is None:
            raise ValueError("Пользователь не найден")
        if target_role != RoleTypes.READER:
            raise ValueError("Блокировать и разблокировать можно только читателей")
        async with self._transaction():
            return await self.user_repo.set_status(user_id, status)