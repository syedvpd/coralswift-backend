from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.common.responses import ApiResponse, ErrorResponse, ok
from app.core.exception_handlers import error_response
from app.database.dependencies import DbSession
from app.health.service import check_database

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=ApiResponse[dict[str, str]])
def health() -> ApiResponse[dict[str, str]]:
    return ok({"status": "ok"})


@router.get("/live", response_model=ApiResponse[dict[str, str]])
def live() -> ApiResponse[dict[str, str]]:
    return ok({"status": "alive"})


@router.get(
    "/ready",
    response_model=ApiResponse[dict[str, str]],
    responses={503: {"model": ErrorResponse}},
)
def ready(request: Request, db: DbSession) -> ApiResponse[dict[str, str]] | JSONResponse:
    if not check_database(db):
        return error_response(
            request,
            503,
            "NOT_READY",
            "Service is not ready",
            [{"component": "database", "status": "unavailable"}],
        )
    return ok({"status": "ready", "database": "ok"})
