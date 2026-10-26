import asyncio
import re

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Forbidden, Unauthorized, InvalidInput, Conflict, UserNotFound
from app.core.security import (
    MAX_PASSWORD_BYTES, MIN_PASSWORD_LENGTH, hash_password, verify_password,
)
from app.core.text import collapse_spaces, normalize_email
from app.models import RoleTypes, User, UserStatus
from app.repositories import GenreRepository, RoleRepository, UserGenreRepository
from app.services.base import BaseService

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_EMAIL_TAKEN = "Пользователь с таким email уже зарегистрирован"

# Фиктивный хеш: проверяем пароль и когда email не найден, чтобы время ответа
# не выдавало, зарегистрирован ли email.
_DUMMY_HASH = hash_password("dummy-password-for-timing")


class UserService(BaseService):
    def __init__(self, session: AsyncSession):
        super().__init__(session)
        self.role_repo = RoleRepository(session)
        self.genre_repo = GenreRepository(session)
        self.user_genre_repo = UserGenreRepository(session)

    async def register_reader(
        self, full_name: str, email: str, password: str, genre_ids: list[int] | None = None
    ) -> User:
        return await self._create_user(
            role=RoleTypes.READER,
            full_name=full_name,
            email=email,
            password=password,
            genre_ids=genre_ids or [],
        )

    async def create_librarian(self, full_name: str, email: str, password: str) -> User:
        return await self._create_user(RoleTypes.LIBRARIAN, full_name, email, password, [])

    async def authenticate(self, email: str, password: str) -> User:
        user = await self.user_repo.get_by_email(normalize_email(email))
        password_hash = user.password_hash if user is not None else _DUMMY_HASH
        # bcrypt блокирует event loop, поэтому выносим в поток
        password_ok = await asyncio.to_thread(verify_password, password, password_hash)
        if user is None or not password_ok:
            raise Unauthorized("Неверный email или пароль")
        if user.status == UserStatus.BLOCKED:
            raise Forbidden("Пользователь заблокирован")
        return user

    async def _create_user(
        self, role: RoleTypes, full_name: str, email: str, password: str, genre_ids: list[int]
    ) -> User:
        full_name = collapse_spaces(full_name)
        email = normalize_email(email)
        if not full_name:
            raise InvalidInput("Имя не может быть пустым")
        if not _EMAIL_RE.match(email):
            raise InvalidInput("Некорректный email")
        if len(password) < MIN_PASSWORD_LENGTH:
            raise InvalidInput(f"Пароль должен быть не короче {MIN_PASSWORD_LENGTH} символов")
        if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
            raise InvalidInput(f"Пароль не должен быть длиннее {MAX_PASSWORD_BYTES} байт")

        genre_ids = await self._validated_genre_ids(genre_ids)
        role_row = await self.role_repo.get_by_name(role)
        if role_row is None:
            raise InvalidInput(f"Роль {role.value} не найдена: заполните справочник ролей")

        password_hash = await asyncio.to_thread(hash_password, password)

        try:
            async with self._transaction():
                if await self.user_repo.get_by_email(email) is not None:
                    raise Conflict(_EMAIL_TAKEN)
                user = await self.user_repo.create(
                    full_name=full_name,
                    email=email,
                    password_hash=password_hash,
                    role_id=role_row.id,
                )
                await self.user_genre_repo.replace(user.id, genre_ids)
        except IntegrityError as e:
            raise Conflict(_EMAIL_TAKEN) from e
        return user

    async def set_interests(self, user_id: int, genre_ids: list[int]) -> list[int]:
        if await self.user_repo.get_by_id(user_id) is None:
            raise UserNotFound("Пользователь не найден")
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
                raise InvalidInput(f"Жанр {genre_id} не найден")
        return unique

    async def block_user(self, user_id: int) -> User:
        return await self._set_reader_status(user_id, UserStatus.BLOCKED)

    async def unblock_user(self, user_id: int) -> User:
        return await self._set_reader_status(user_id, UserStatus.ACTIVE)

    async def list_users(self, limit: int = 50, offset: int = 0) -> list[User]:
        return await self.user_repo.list_users(max(1, min(limit, 200)), max(0, offset))

    async def _set_reader_status(self, user_id: int, status: UserStatus) -> User:
        target_role = await self.user_repo.get_role_name(user_id)
        if target_role is None:
            raise UserNotFound("Пользователь не найден")
        if target_role != RoleTypes.READER:
            raise InvalidInput("Блокировать и разблокировать можно только читателей")
        async with self._transaction():
            return await self.user_repo.set_status(user_id, status)
        
    async def get_role_name(self, role_id: int) -> RoleTypes | None:
        return await self.user_repo.get_role_name(role_id)