"""Общие данные рекомендаций без зависимостей от ML-библиотек."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Book:
    book_id: int
    title: str
    description: str = ""
    genres: tuple[str, ...] = ()
    published: bool = True

    @property
    def text(self) -> str:
        # Жанры идут перед описанием, чтобы не потеряться при усечении токенов.
        return f"{self.title}. Genres: {', '.join(self.genres)}. {self.description}"


@dataclass(frozen=True, slots=True)
class Rating:
    user_id: int
    book_id: int
    score: float


@dataclass(frozen=True)
class UserProfile:
    user_id: int
    interests: tuple[str, ...] = ()
    excluded_book_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class Recommendation:
    book_id: int
    title: str
    score: float
