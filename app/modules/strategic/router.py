from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import JSONResponse

from app.common.responses import ApiResponse, ErrorResponse
from app.core.config import Settings, get_settings
from app.core.protection import SubmissionGuards
from app.database.dependencies import DbSession
from app.modules.enquiries.schemas import SubmissionOut
from app.modules.enquiries.submission import IdempotencyKeyHeader, execute_submission
from app.modules.strategic.schemas import StrategicEnquiryIn
from app.modules.strategic.service import create_strategic_enquiry

router = APIRouter(prefix="/enquiries", tags=["enquiries"])


@router.post(
    "/strategic",
    status_code=201,
    response_model=ApiResponse[SubmissionOut],
    dependencies=SubmissionGuards,
    responses={422: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
    summary="Submit a confidential strategic / merger / integration enquiry",
)
def submit_strategic(
    payload: StrategicEnquiryIn,
    request: Request,
    db: DbSession,
    settings: Annotated[Settings, Depends(get_settings)],
    background: BackgroundTasks,
    idempotency_key: IdempotencyKeyHeader = None,
) -> JSONResponse:
    """Submission only. No endpoint reads or lists strategic records; staff access is Phase 3."""
    return execute_submission(
        request=request,
        db=db,
        settings=settings,
        background=background,
        payload=payload,
        idem_key=idempotency_key,
        create=lambda: create_strategic_enquiry(db, settings, payload),
    )
