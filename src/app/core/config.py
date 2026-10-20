from decimal import Decimal
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # В .env позже появятся переменные для Docker (POSTGRES_USER и т.п.),
        # которых нет в этом классе. Без ignore pydantic падает на лишних ключах.
        extra="ignore",
    )

    # БД
    database_url: str
    sql_echo: bool = False

    # Бизнес-правила
    reservation_hours: int
    loan_days: int
    max_active_reservations: int
    fine_per_day: Decimal
    fine_lost: Decimal
    subscription_price: Decimal
    subscription_days: int = 30

    # JWT. Секрет без значения по умолчанию: без него приложение не стартует.
    jwt_secret_key: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60


@lru_cache
def get_settings() -> Settings:
    """Один экземпляр на процесс: .env читается один раз."""
    return Settings()  # type: ignore[call-arg]