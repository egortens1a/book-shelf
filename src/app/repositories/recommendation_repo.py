"""Данные рекомендаций читает API; gRPC-сервис не имеет доступа к БД."""

from dataclasses import dataclass

from sqlalchemy import select, union
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (Book, BookCopy, BookStatus, Genre, Rating, ReadingProgress,
                        Reservation, ReservationStatus, UserGenre)
from recsys.domain import Book as RecommendationBook, Rating as RecommendationRating


@dataclass(frozen=True)
class RecommendationData:
    books: list[RecommendationBook]
    ratings: list[RecommendationRating]
    interests: list[str]
    excluded: list[int]


class RecommendationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def load(self, user_id: int) -> RecommendationData:
        # Архивные книги нужны как история предпочтений, но не как кандидаты.
        books = (await self.session.scalars(
            select(Book).where(Book.status != BookStatus.DRAFT)
            .options(selectinload(Book.genres)).order_by(Book.id)
        )).all()
        ratings = (await self.session.execute(
            select(Rating.user_id, Rating.book_id, Rating.score)
            .join(Book, Book.id == Rating.book_id).where(Book.status != BookStatus.DRAFT)
            .order_by(Rating.user_id, Rating.book_id)
        )).all()
        interests = (await self.session.scalars(
            select(Genre.name).join(UserGenre, UserGenre.genre_id == Genre.id)
            .where(UserGenre.user_id == user_id).order_by(Genre.id)
        )).all()
        finished = select(ReadingProgress.book_id).where(
            ReadingProgress.user_id == user_id, ReadingProgress.finished_at.is_not(None),
        )
        returned = select(BookCopy.book_id).join(Reservation, Reservation.copy_id == BookCopy.id).where(
            Reservation.user_id == user_id, Reservation.status == ReservationStatus.RETURNED,
        )
        excluded = (await self.session.scalars(union(finished, returned))).all()
        return RecommendationData(
            books=[RecommendationBook(b.id, b.title, b.description, tuple(sorted(g.name for g in b.genres)),
                                      b.status == BookStatus.PUBLISHED) for b in books],
            ratings=[RecommendationRating(r.user_id, r.book_id, r.score) for r in ratings],
            interests=list(interests), excluded=sorted(excluded),
        )
