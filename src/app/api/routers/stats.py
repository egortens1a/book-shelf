"""Сводная статистика библиотеки. Доступна только администратору."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_stats_service, require_role
from app.models import RoleTypes
from app.schemas.stats import CatalogStatsRead, TopBookRead
from app.services.stats_service import StatsService

Stats = Annotated[StatsService, Depends(get_stats_service)]

# Роль проверяется на уровне роутера: отдельных прав у этих эндпоинтов нет.
router = APIRouter(
    prefix="/admin",
    tags=["stats"],
    dependencies=[Depends(require_role(RoleTypes.ADMIN))],
)


@router.get("/stats", response_model=CatalogStatsRead)
async def catalog_stats(stats: Stats):
    """Сводка по всей библиотеке."""
    return await stats.get_catalog_stats()


@router.get("/stats/top", response_model=list[TopBookRead])
async def top_books(
    stats: Stats,
    genre_id: Annotated[int, Query(description="Жанр, внутри которого строится рейтинг")],
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
):
    """Книги жанра по убыванию средней оценки.

    Учитываются только опубликованные книги, у которых есть хотя бы одна
    оценка. При равной средней выше та, у которой оценок больше.
    """
    rows = await stats.top_k_book_by_genre(k=limit, genre_id=genre_id)
    return [
        TopBookRead(title=title, average_score=average, ratings_count=count)
        for title, average, count in rows
    ]
