from typing import Protocol


class SubscriptionChecker(Protocol):
    async def __call__(self, user_id: int) -> bool:
        """True, если у читателя сейчас активная подписка."""
        ...


class ReturnedBookChecker(Protocol):
    async def __call__(self, user_id: int, book_id: int) -> bool:
        """True, если читатель вернул бумажный экземпляр этой книги."""
        ...