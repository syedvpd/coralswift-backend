"""Central exception handling. No stack traces or internals ever reach the client."""

import logging
from collections.abc import Mapping
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.common.responses import error_body
from app.core.constants import REQUEST_ID_HEADER
from app.core.exceptions import AppError

logger = logging.getLogger("app.errors")

_HTTP_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    429: "TOO_MANY_REQUESTS",
}


def error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    out = dict(headers or {})
    # The 500 handler runs outside the request-context middleware, so set the header here too.
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        out[REQUEST_ID_HEADER] = request_id
    return JSONResponse(error_body(code, message, details), status_code=status_code, headers=out)


async def app_error_handler(request: Request, exc: Exception) -> JSONResponse:
    err = cast(AppError, exc)
    return error_response(
        request, err.status_code, err.code, err.message, err.details, headers=err.headers
    )


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    err = cast(StarletteHTTPException, exc)
    code = _HTTP_CODES.get(err.status_code, "HTTP_ERROR")
    message = err.detail if isinstance(err.detail, str) else "Request failed"
    return error_response(request, err.status_code, code, message, headers=err.headers)


async def validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    err = cast(RequestValidationError, exc)
    # Deliberately drop 'input'/'ctx': they can echo submitted (possibly sensitive) values.
    details = [
        {
            "source": str(e["loc"][0]) if e["loc"] else "",
            "field": ".".join(str(p) for p in e["loc"][1:]),
            "message": e["msg"],
            "type": e["type"],
        }
        for e in err.errors()
    ]
    return error_response(request, 422, "VALIDATION_ERROR", "Validation failed", details)


async def database_unavailable_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("database unavailable", exc_info=exc)
    return error_response(request, 503, "DATABASE_UNAVAILABLE", "Service temporarily unavailable")


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "unhandled exception",
        exc_info=exc,
        extra={
            "request_id": getattr(request.state, "request_id", None),
            "method": request.method,
            "path": request.url.path,
        },
    )
    return error_response(request, 500, "INTERNAL_ERROR", "An unexpected error occurred")


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(OperationalError, database_unavailable_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
