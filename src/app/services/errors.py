class ServiceError(Exception):
    """Нарушение бизнес-правила.

    Сервисы поднимают только такие ошибки: вызывающий код не должен
    разбирать исключения SQLAlchemy, чтобы понять, что пошло не так.
    """


class UserNotFound(ServiceError):
    pass


class SubscriptionAlreadyQueued(ServiceError):
    pass
