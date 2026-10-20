from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from logging import getLogger

logger = getLogger(__name__)


from app.core.errors import (
    Conflict,
    Forbidden,
    InvalidInput,
    NotFound,
    ServiceError,
    Unauthorized,
)


def _make_handler(status_code: int, headers: dict[str, str] | None = None):
    async def handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=status_code,
            content={"detail": str(exc) or exc.__class__.__name__},
            headers=headers,
        )

    return handler

async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )
    

def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(Unauthorized, _make_handler(status.HTTP_401_UNAUTHORIZED))
    app.add_exception_handler(Forbidden, _make_handler(status.HTTP_403_FORBIDDEN))
    app.add_exception_handler(NotFound, _make_handler(status.HTTP_404_NOT_FOUND))
    app.add_exception_handler(Conflict, _make_handler(status.HTTP_409_CONFLICT))
    app.add_exception_handler(InvalidInput, _make_handler(status.HTTP_422_UNPROCESSABLE_CONTENT))
    app.add_exception_handler(ServiceError, _make_handler(status.HTTP_400_BAD_REQUEST))
    
    app.add_exception_handler(Exception, unhandled_exception_handler)