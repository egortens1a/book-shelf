"""Схемы рекомендаций. Контракт зафиксирован в ЛР2, в ЛР3 данные придут из gRPC."""

from pydantic import BaseModel, Field


class RecommendationRead(BaseModel):
    book_id: int
    title: str
    score: float


class RecommendationsRead(BaseModel):
    items: list[RecommendationRead] = Field(default_factory=list)