class ServiceError(Exception):
    """Нарушение бизнес-правила.

    Сервисы поднимают только такие ошибки: вызывающий код не должен
    разбирать исключения SQLAlchemy, чтобы понять, что пошло не так.
    """


class UserNotFound(ServiceError):
    pass


class SubscriptionAlreadyQueued(ServiceError):
    pass


class BookNotFound(ServiceError):
    pass


class BookNotPublished(ServiceError):
    pass


class CopyNotFound(ServiceError):
    pass


class CopyNotAvailable(ServiceError):
    pass


class DuplicateInventoryNumber(ServiceError):
    pass


class ReservationNotFound(ServiceError):
    pass


class InvalidReservationState(ServiceError):
    pass


class PickupExpired(ServiceError):
    pass


class NoCopyAvailable(ServiceError):
    pass


class NoActiveSubscription(ServiceError):
    pass


class TooManyReservations(ServiceError):
    pass


class AlreadyReserved(ServiceError):
    pass


class HasOverdueLoan(ServiceError):
    pass


class HasUnpaidFine(ServiceError):
    pass


class FineNotFound(ServiceError):
    pass
