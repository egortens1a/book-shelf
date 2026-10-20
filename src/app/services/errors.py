"""
Unauthorized -> 401    
Forbidden -> 403    
NotFound -> 404
Conflict     -> 409    
InvalidInput -> 422
"""


class ServiceError(Exception):
    """Нарушение бизнес-правила.

    Сервисы поднимают только такие ошибки: вызывающий код не должен
    разбирать исключения SQLAlchemy, чтобы понять, что пошло не так.
    """


# Базовые классы

class Unauthorized(ServiceError):
    """401: нет или невалидный токен, неверный email или пароль."""


class Forbidden(ServiceError):
    """403: не та роль, пользователь заблокирован, нет права на действие."""


class NotFound(ServiceError):
    """404: сущность не найдена (в том числе чужая бронь)."""


class Conflict(ServiceError):
    """409: конфликт состояния, дубликат, нарушение связей."""


class InvalidInput(ServiceError):
    """422: невалидные данные, не пойманные Pydantic."""


# 404

class UserNotFound(NotFound):
    pass


class BookNotFound(NotFound):
    pass


class CopyNotFound(NotFound):
    pass


class ReservationNotFound(NotFound):
    pass


class FineNotFound(NotFound):
    pass


class AuthorNotFound(NotFound):
    pass


class GenreNotFound(NotFound):
    pass


# 403 

class NoActiveSubscription(Forbidden):
    pass


class HasOverdueLoan(Forbidden):
    pass


class HasUnpaidFine(Forbidden):
    pass


# 409

class SubscriptionAlreadyQueued(Conflict):
    pass


class BookNotPublished(Conflict):
    pass


class CopyNotAvailable(Conflict):
    pass


class DuplicateInventoryNumber(Conflict):
    pass


class InvalidReservationState(Conflict):
    pass


class PickupExpired(Conflict):
    pass


class NoCopyAvailable(Conflict):
    pass


class TooManyReservations(Conflict):
    pass


class AlreadyReserved(Conflict):
    pass