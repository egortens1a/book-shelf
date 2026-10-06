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


class CopyNotFound(ServiceError):
    pass


class CopyNotAvailable(ServiceError):
    pass


class DuplicateInventoryNumber(ServiceError):
    pass
