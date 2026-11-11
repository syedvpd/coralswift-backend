from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Request
from fastapi.responses import JSONResponse

from app.common.responses import ApiResponse, ErrorResponse, ok
from app.core.config import Settings, get_settings
from app.core.exceptions import NotFoundError
from app.core.protection import SubmissionGuards, rate_limit
from app.database.dependencies import DbSession
from app.modules.enquiries.schemas import ContactEnquiryIn, StatusOut, SubmissionOut
from app.modules.enquiries.service import create_contact_enquiry, find_status
from app.modules.enquiries.submission import IdempotencyKeyHeader, execute_submission

router = APIRouter(prefix="/enquiries", tags=["enquiries"])
SettingsDep = Annotated[Settings, Depends(get_settings)]
_ERRORS: dict[int | str, dict[str, Any]] = {
    403: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    413: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
    429: {"model": ErrorResponse},
}


@router.post(
    "/contact",
    status_code=201,
    response_model=ApiResponse[SubmissionOut],
    dependencies=SubmissionGuards,
    responses=_ERRORS,
    summary="Submit a general contact enquiry",
)
def submit_contact(
    payload: ContactEnquiryIn,
    request: Request,
    db: DbSession,
    settings: SettingsDep,
    background: BackgroundTasks,
    idempotency_key: IdempotencyKeyHeader = None,
) -> JSONResponse:
    return execute_submission(
        request=request,
        db=db,
        settings=settings,
        background=background,
        payload=payload,
        idem_key=idempotency_key,
        create=lambda: create_contact_enquiry(db, settings, payload),
    )


@router.get(
    "/{reference_number}/status",
    response_model=ApiResponse[StatusOut],
    dependencies=[Depends(rate_limit("status", 3))],
    responses={404: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
    summary="Public status lookup (reference + lookup token)",
)
def enquiry_status(
    reference_number: str,
    db: DbSession,
    settings: SettingsDep,
    x_lookup_token: Annotated[
        str | None, Header(description="Token returned at submission")
    ] = None,
) -> ApiResponse[StatusOut]:
    """Returns only type, status and submission time. Unknown reference and wrong token give the
    same 404, so references cannot be enumerated."""
    enquiry = find_status(db, settings, reference_number, x_lookup_token)
    if enquiry is None:
        raise NotFoundError("Enquiry not found")
    return ok(
        StatusOut(
            reference_number=enquiry.reference_number,
            enquiry_type=enquiry.enquiry_type,
            status=enquiry.status,
            submitted_at=enquiry.created_at,
        )
    )
