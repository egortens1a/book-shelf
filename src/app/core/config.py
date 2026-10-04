from decimal import Decimal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str
    reservation_hours: int
    loan_days: int
    max_active_reservations: int
    fine_per_day: Decimal
    fine_lost: Decimal
    subscription_price: Decimal
    
    
def get_settings() -> Settings:
    return Settings() # type: ignore