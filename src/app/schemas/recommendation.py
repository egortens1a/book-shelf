"""HTTP-контракт рекомендаций: результат отдельного gRPC-сервиса (ЛР3)."""

from pydantic import BaseModel, Field


class RecommendationRead(BaseModel):
    book_id: int
    title: str
    score: float


class RecommendationsRead(BaseModel):
    items: list[RecommendationRead] = Field(default_factory=list)
