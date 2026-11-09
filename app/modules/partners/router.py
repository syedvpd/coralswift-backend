from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import JSONResponse

from app.common.responses import ApiResponse, ErrorResponse
from app.core.config import Settings, get_settings
from app.core.protection import SubmissionGuards
from app.database.dependencies import DbSession
from app.modules.enquiries.schemas import SubmissionOut
from app.modules.enquiries.submission import IdempotencyKeyHeader, execute_submission
from app.modules.partners.schemas import PartnerApplicationIn
from app.modules.partners.service import create_partner_application

router = APIRouter(prefix="/enquiries", tags=["enquiries"])


@router.post(
    "/partner",
    status_code=201,
    response_model=ApiResponse[SubmissionOut],
    dependencies=SubmissionGuards,
    responses={422: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
    summary="Submit a partner application",
)
def submit_partner(
    payload: PartnerApplicationIn,
    request: Request,
    db: DbSession,
    settings: Annotated[Settings, Depends(get_settings)],
    background: BackgroundTasks,
    idempotency_key: IdempotencyKeyHeader = None,
) -> JSONResponse:
    """Records the submission for human review. The proposed screening criteria (3 years, 50
    personnel, INR 2 crore) are NOT evaluated here; submitting is not an approval or an award."""
    return execute_submission(
        request=request,
        db=db,
        settings=settings,
        background=background,
        payload=payload,
        idem_key=idempotency_key,
        create=lambda: create_partner_application(db, settings, payload),
    )
