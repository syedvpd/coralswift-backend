"""Response envelope shared by all endpoints."""

from typing import Any

from pydantic import BaseModel


class ApiResponse[T](BaseModel):
    success: bool = True
    message: str = "Operation completed successfully"
    data: T | None = None
    meta: dict[str, Any] | None = None


class ErrorDetail(BaseModel):
    code: str
    details: list[dict[str, Any]] = []


class ErrorResponse(BaseModel):
    success: bool = False
    message: str
    error: ErrorDetail


def ok(
    data: Any = None,
    message: str = "Operation completed successfully",
    meta: dict[str, Any] | None = None,
) -> ApiResponse[Any]:
    return ApiResponse[Any](message=message, data=data, meta=meta)


def error_body(
    code: str, message: str, details: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    return ErrorResponse(
        message=message, error=ErrorDetail(code=code, details=details or [])
    ).model_dump()
