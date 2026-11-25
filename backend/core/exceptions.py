import logging
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """Register consistent JSON exception handlers."""

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": "http_error",
                "detail": exc.detail,
                "status_code": exc.status_code,
                "path": request.url.path,
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_server_error",
                "detail": "An unexpected error occurred.",
                "status_code": 500,
                "path": request.url.path,
            },
        )
