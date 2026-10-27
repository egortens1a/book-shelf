"""Схемы сводной статистики."""

from decimal import Decimal

from pydantic import BaseModel


class CatalogStatsRead(BaseModel):
    """Числа по каталогу, пользователям, бронированию, подпискам и штрафам.

    Разрезы приходят из сервиса словарями «значение енума -> количество»,
    поэтому типизируются как dict[str, int], а не перечислением полей:
    состав статусов задаётся моделями и может пополниться.
    """

    books_by_status: dict[str, int]
    books_by_access_type: dict[str, int]
    authors_total: int
    genres_total: int
    users_by_role: dict[str, int]
    users_by_status: dict[str, int]
    ratings_count: int
    ratings_average: float | None = None
    reservations_by_status: dict[str, int]
    subscriptions_by_status: dict[str, int]
    fines_by_status: dict[str, int]
    unpaid_fines_total: Decimal


class TopBookRead(BaseModel):
    """Строка рейтинга книг внутри жанра.

    Репозиторий отдаёт кортежи (название, средняя оценка, число оценок),
    поэтому объект собирается в роутере явно.
    """

    title: str
    average_score: float
    ratings_count: int
