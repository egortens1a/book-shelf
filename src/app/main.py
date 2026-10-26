"""Точка входа API Service (BookShelf)"""

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator


import uvicorn
from fastapi import FastAPI


from app.core.error_handlers import register_exception_handlers
from app.core.db import engine

from app.api.routers import auth, me, admin, catalog, directory, ratings

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # startup: сюда при необходимости (например, прогрев соединений)
    yield
    # shutdown: корректно закрываем пул соединений
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="BookShelf API",
        version="0.1.0",
        lifespan=lifespan,
    )

    register_exception_handlers(app)

    app.include_router(auth.router) # /register, /login
    app.include_router(me.router) # /me, /me/interests, /me/recommendations (в будущем)
    app.include_router(admin.router)       # /admin/...

    app.include_router(catalog.reader_router)     # /books, /genres, /authors
    app.include_router(catalog.librarian_router)    # /librarian/books/...
    
    app.include_router(directory.router)
    app.include_router(directory.router_admin)

    app.include_router(ratings.router)     # /books/{id}/rating(s)

    @app.get("/health", tags=["service"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app

app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True
    )