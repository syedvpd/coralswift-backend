from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import JSONResponse

from app.common.responses import ApiResponse, ErrorResponse
from app.core.config import Settings, get_settings
from app.core.protection import SubmissionGuards
from app.database.dependencies import DbSession
from app.modules.enquiries.schemas import SubmissionOut
from app.modules.enquiries.submission import IdempotencyKeyHeader, execute_submission
from app.modules.projects.schemas import ProjectEnquiryIn
from app.modules.projects.service import create_project_enquiry

router = APIRouter(prefix="/enquiries", tags=["enquiries"])


@router.post(
    "/project",
    status_code=201,
    response_model=ApiResponse[SubmissionOut],
    dependencies=SubmissionGuards,
    responses={
        403: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        413: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
    },
    summary="Submit a project enquiry (IT or Non-IT category)",
)
def submit_project(
    payload: ProjectEnquiryIn,
    request: Request,
    db: DbSession,
    settings: Annotated[Settings, Depends(get_settings)],
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
        create=lambda: create_project_enquiry(db, settings, payload),
    )
