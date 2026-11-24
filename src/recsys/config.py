"""Настройки отдельного gRPC-процесса из окружения или .env."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from recsys.embeddings import DEFAULT_MODEL


class ServerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RECOMMENDATIONS_", env_file=".env",
                                     env_file_encoding="utf-8", extra="ignore")
    host: str = "127.0.0.1"
    port: int = Field(default=50051, ge=1, le=65535)
    cache_dir: str = ".cache/models"
    model: str = DEFAULT_MODEL
    cf_weight: float = Field(default=0.25, ge=0, le=1)
