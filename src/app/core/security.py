from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import get_settings
from app.core.errors import Unauthorized, UserNotFound

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_BYTES = 72

settings = get_settings()

# Пароли

def hash_password(password: str) -> str:
    """bcrypt: хеш с солью, соль хранится внутри самого хеша"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except UserNotFound:
        return False


# ---------- JWT ----------

def create_access_token(user_id: int, role_id: int) -> str:
    """Подписанный токен. В claims только id и роль, пароль и email не кладём."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role_id": role_id,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    """Проверяет подпись и срок, возвращает payload"""
    try:
        return jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],  # алгоритм задаём явно
            options={"require": ["exp", "sub"]},
        )
    except jwt.ExpiredSignatureError:
        raise Unauthorized("Token expired") from None
    except jwt.InvalidTokenError:
        raise Unauthorized("Invalid token") from None