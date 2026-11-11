"""Application review workflow (checklist, exceptions, stage owners, reconsideration) and
enquiry assessment outcomes. Decisions are always human: nothing here evaluates a score."""

import enum
import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.pagination import PageDep, page_meta
from app.common.responses import ApiResponse, ErrorResponse, ok
from app.common.utilities import utcnow
from app.common.validation import Long, Short
from app.core.config import Settings, get_settings
from app.core.exceptions import AppError, NotFoundError
from app.database.dependencies import DbSession
from app.modules.admin import lookups
from app.modules.admin import service as admin_service
from app.modules.applications.constants import TERMINAL, PortalStatus
from app.modules.applications.models import ApplicationStatusHistory, PortalApplication
from app.modules.auth.constants import StaffRole, UserStatus, UserType
from app.modules.auth.dependencies import (
    ReviewerDep,
    StaffContext,
    SuperAdminDep,
    require_staff,
)
from app.modules.auth.models import User
from app.modules.enquiries.activity import log_activity
from app.modules.enquiries.constants import ActorType
from app.modules.notifications.constants import NotificationType, TemplateKey
from app.modules.notifications.service import dispatch_notifications, queue_notification
from app.modules.review_workflow.models import (
    ApplicationException,
    ApplicationStageOwner,
    ChecklistResult,
    EnquiryAssessment,
    ReviewChecklistItem,
)
from app.modules.reviews import service as review_service

SettingsDep = Annotated[Settings, Depends(get_settings)]
_ERR: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}
AdminDep = Annotated[
    StaffContext,
    Depends(require_staff(StaffRole.SUPER_ADMINISTRATOR, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)),
]
router = APIRouter(prefix="/reviewer/applications", tags=["reviewer-workflow"])
enquiry = APIRouter(prefix="/admin/enquiries", tags=["admin-enquiries"])

# Stages a reviewer can work in (draft and the two terminal states are not stages).
STAGES = frozenset(
    {
        PortalStatus.SUBMITTED,
        PortalStatus.ELIGIBILITY_VERIFICATION,
        PortalStatus.CAPABILITY_REVIEW,
        PortalStatus.COMMERCIAL_LEGAL_REVIEW,
        PortalStatus.PILOT_ONBOARDING,
        PortalStatus.SCALE_UP,
    }
)


# ------------------------------------------------------------------ schemas
class ChecklistItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: PortalStatus
    name: Short
    result: ChecklistResult = ChecklistResult.PENDING
    note: Long | None = None

    @model_validator(mode="after")
    def _valid(self) -> "ChecklistItemIn":
        if self.stage not in STAGES:
            raise ValueError("stage must be one of the six allocation stages")
        if self.result is ChecklistResult.FAILED and not self.note:
            raise ValueError("a reviewer note is required when an item fails")
        return self


class ChecklistIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ChecklistItemIn] = Field(min_length=1, max_length=100)


class ChecklistItemOut(BaseModel):
    id: uuid.UUID
    stage: PortalStatus
    name: str
    result: ChecklistResult
    note: str | None
    updated_by_name: str | None
    updated_at: datetime


class ExceptionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule: Short
    reason: Long


class ExceptionOut(BaseModel):
    id: uuid.UUID
    rule: str
    reason: str
    approver_id: uuid.UUID
    approver_name: str | None
    created_at: datetime


class StageOwnerIn(BaseModel):
    """Omitted = unchanged; null clears."""

    model_config = ConfigDict(extra="forbid")

    owner_user_id: uuid.UUID | None = None
    notes: Long | None = None


class StageOwnerOut(BaseModel):
    stage: PortalStatus
    owner_user_id: uuid.UUID | None
    owner_name: str | None
    notes: str | None
    updated_at: datetime


class ReviewWorkflowOut(BaseModel):
    checklist: list[ChecklistItemOut]
    exceptions: list[ExceptionOut]
    stage_owners: list[StageOwnerOut]


class ReopenIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to_status: PortalStatus
    reason: Long

    @field_validator("to_status")
    @classmethod
    def _stage(cls, v: PortalStatus) -> PortalStatus:
        if v not in STAGES:
            raise ValueError("to_status must be one of the six allocation stages")
        return v


# ------------------------------------------------------------------ helpers
def _workflow(db: Session, app: PortalApplication) -> ReviewWorkflowOut:
    items = list(
        db.execute(
            select(ReviewChecklistItem)
            .where(ReviewChecklistItem.application_id == app.id)
            .order_by(ReviewChecklistItem.stage, ReviewChecklistItem.name)
        ).scalars()
    )
    excs = list(
        db.execute(
            select(ApplicationException)
            .where(ApplicationException.application_id == app.id)
            .order_by(ApplicationException.created_at)
        ).scalars()
    )
    owners = list(
        db.execute(
            select(ApplicationStageOwner).where(ApplicationStageOwner.application_id == app.id)
        ).scalars()
    )
    names = lookups.user_names(
        db,
        [i.updated_by for i in items]
        + [e.approver_id for e in excs]
        + [o.owner_user_id for o in owners if o.owner_user_id],
    )
    return ReviewWorkflowOut(
        checklist=[
            ChecklistItemOut(
                id=i.id,
                stage=i.stage,
                name=i.name,
                result=i.result,
                note=i.note,
                updated_by_name=names.get(i.updated_by),
                updated_at=i.updated_at,
            )
            for i in items
        ],
        exceptions=[
            ExceptionOut(
                id=e.id,
                rule=e.rule,
                reason=e.reason,
                approver_id=e.approver_id,
                approver_name=names.get(e.approver_id),
                created_at=e.created_at,
            )
            for e in excs
        ],
        stage_owners=[
            StageOwnerOut(
                stage=o.stage,
                owner_user_id=o.owner_user_id,
                owner_name=names.get(o.owner_user_id) if o.owner_user_id else None,
                notes=o.notes,
                updated_at=o.updated_at,
            )
            for o in owners
        ],
    )


def _audit(
    db: Session, staff: StaffContext, app: PortalApplication, action: str, **meta: Any
) -> None:
    log_activity(
        db,
        "portal_application",
        app.id,
        action,
        meta,
        ActorType.REVIEWER,
        actor_user_id=staff.user.id,
        organization_id=app.organization_id,
    )


# ------------------------------------------------------------------ routes
@router.get(
    "/{application_id}/review",
    response_model=ApiResponse[ReviewWorkflowOut],
    responses=_ERR,
    summary="Checklist, approved exceptions and per-stage owners/notes",
)
def get_review(
    application_id: uuid.UUID, staff: ReviewerDep, db: DbSession
) -> ApiResponse[ReviewWorkflowOut]:
    app = review_service.get_reviewable(db, staff, application_id)
    return ok(_workflow(db, app))


@router.put(
    "/{application_id}/checklist",
    response_model=ApiResponse[ReviewWorkflowOut],
    responses=_ERR,
    summary="Record checklist answers (pass/fail/not_applicable + note; no scoring)",
)
def put_checklist(
    application_id: uuid.UUID, payload: ChecklistIn, staff: ReviewerDep, db: DbSession
) -> ApiResponse[ReviewWorkflowOut]:
    app = review_service.get_reviewable(db, staff, application_id, lock=True)
    seen: set[tuple[PortalStatus, str]] = set()
    for item in payload.items:
        key = (item.stage, item.name)
        if key in seen:
            raise AppError("Duplicate checklist item", status_code=422, code="DUPLICATE_ITEM")
        seen.add(key)
        row = db.execute(
            select(ReviewChecklistItem).where(
                ReviewChecklistItem.application_id == app.id,
                ReviewChecklistItem.stage == item.stage,
                ReviewChecklistItem.name == item.name,
            )
        ).scalar_one_or_none()
        if row is None:
            row = ReviewChecklistItem(
                application_id=app.id, stage=item.stage, name=item.name, updated_by=staff.user.id
            )
            db.add(row)
        row.result, row.note, row.updated_by = item.result, item.note, staff.user.id
    _audit(db, staff, app, "application.checklist_updated", items=len(payload.items))
    db.commit()
    return ok(_workflow(db, app), "Checklist saved")


@router.post(
    "/{application_id}/exceptions",
    status_code=201,
    response_model=ApiResponse[ReviewWorkflowOut],
    responses=_ERR,
    summary="Record an approved exception (super administrator is the approver)",
)
def add_exception(
    application_id: uuid.UUID, payload: ExceptionIn, staff: SuperAdminDep, db: DbSession
) -> ApiResponse[ReviewWorkflowOut]:
    app = review_service.get_reviewable(db, staff, application_id, lock=True)
    db.add(
        ApplicationException(
            application_id=app.id,
            rule=payload.rule,
            reason=payload.reason,
            approver_id=staff.user.id,
            created_at=utcnow(),
        )
    )
    _audit(db, staff, app, "application.exception_approved", rule=payload.rule)
    db.commit()
    return ok(_workflow(db, app), "Exception recorded")


@router.put(
    "/{application_id}/stage-owners/{stage}",
    response_model=ApiResponse[ReviewWorkflowOut],
    responses=_ERR,
    summary="Set the owner and notes of one stage (omit = unchanged, null clears)",
)
def put_stage_owner(
    application_id: uuid.UUID,
    stage: PortalStatus,
    payload: StageOwnerIn,
    staff: ReviewerDep,
    db: DbSession,
) -> ApiResponse[ReviewWorkflowOut]:
    if stage not in STAGES:
        raise AppError("Unknown stage", status_code=422, code="INVALID_STAGE")
    app = review_service.get_reviewable(db, staff, application_id, lock=True)
    changes = payload.model_dump(exclude_unset=True)
    owner_id = changes.get("owner_user_id")
    if owner_id is not None:
        owner = db.get(User, owner_id)
        valid = (
            owner is not None
            and owner.user_type is UserType.STAFF
            and owner.status is UserStatus.ACTIVE
            and owner.staff_role in (StaffRole.PARTNER_REVIEWER, StaffRole.SUPER_ADMINISTRATOR)
        )
        if not valid:
            raise NotFoundError("Reviewer not found")
    row = db.get(ApplicationStageOwner, (app.id, stage))
    if row is None:
        row = ApplicationStageOwner(
            application_id=app.id, stage=stage, updated_by=staff.user.id, updated_at=utcnow()
        )
        db.add(row)
    for field, value in changes.items():
        setattr(row, field, value)
    row.updated_by, row.updated_at = staff.user.id, utcnow()
    _audit(db, staff, app, "application.stage_owner_updated", stage=stage.value)
    db.commit()
    return ok(_workflow(db, app), "Stage updated")


@router.post(
    "/{application_id}/reopen",
    response_model=ApiResponse[ReviewWorkflowOut],
    responses=_ERR,
    summary="Reconsideration: reopen a rejected or withdrawn application at a stage (super admin)",
)
def reopen(
    application_id: uuid.UUID,
    payload: ReopenIn,
    request: Request,
    staff: SuperAdminDep,
    db: DbSession,
    settings: SettingsDep,
    background: BackgroundTasks,
) -> ApiResponse[ReviewWorkflowOut]:
    app = review_service.get_reviewable(db, staff, application_id, lock=True)
    if app.status not in TERMINAL:
        raise AppError(
            "Only rejected or withdrawn applications can be reopened",
            status_code=409,
            code="NOT_REOPENABLE",
        )
    previous = app.status
    app.status, app.resume_status, app.decided_at = payload.to_status, None, None
    db.add(
        ApplicationStatusHistory(
            application_id=app.id,
            from_status=previous,
            to_status=payload.to_status,
            actor_type=ActorType.REVIEWER.value,
            actor_user_id=staff.user.id,
            reason=f"Reconsideration: {payload.reason}",
            partner_note="Your application was reopened for reconsideration.",
            created_at=utcnow(),
        )
    )
    _audit(
        db,
        staff,
        app,
        "application.reopened",
        **{"from": previous.value, "to": payload.to_status.value},
    )
    queue_notification(
        db,
        recipient=_partner_email(db, app),
        kind=NotificationType.APPLICATION,
        template=TemplateKey.APPLICATION_STATUS_CHANGED,
        context={"reference": app.reference, "status_label": "Reopened for reconsideration"},
        dedupe_key=f"reopen:{app.id}:{utcnow().isoformat()}",
    )
    db.commit()
    background.add_task(
        dispatch_notifications,
        request.app.state.sessionmaker,
        request.app.state.email_sender,
        settings,
    )
    return ok(_workflow(db, app), "Application reopened")


def _partner_email(db: Session, app: PortalApplication) -> str:
    creator = db.get(User, app.created_by)
    return creator.email if creator else ""


# ================================================ enquiry assessment outcome


class AssessmentOutcome(enum.StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_CLARIFICATION = "needs_clarification"
    PENDING = "pending"


class AssessmentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: AssessmentOutcome
    note: Long | None = None


class AssessmentOut(BaseModel):
    id: uuid.UUID
    outcome: str
    note: str | None
    assessed_by_name: str | None
    assessed_at: datetime


def _assessments(db: Session, enquiry_id: uuid.UUID) -> list[AssessmentOut]:
    rows = list(
        db.execute(
            select(EnquiryAssessment)
            .where(EnquiryAssessment.enquiry_id == enquiry_id)
            .order_by(EnquiryAssessment.assessed_at.desc(), EnquiryAssessment.id)
        ).scalars()
    )
    names = lookups.user_names(db, (r.assessed_by for r in rows))
    return [
        AssessmentOut(
            id=r.id,
            outcome=r.outcome,
            note=r.note,
            assessed_by_name=names.get(r.assessed_by),
            assessed_at=r.assessed_at,
        )
        for r in rows
    ]


@enquiry.post(
    "/{enquiry_id}/assessment",
    status_code=201,
    response_model=ApiResponse[list[AssessmentOut]],
    responses=_ERR,
    summary="Record an assessment outcome (history kept; strategic only for permitted staff)",
)
def add_assessment(
    enquiry_id: uuid.UUID, payload: AssessmentIn, staff: AdminDep, db: DbSession
) -> ApiResponse[list[AssessmentOut]]:
    enq = admin_service.get_visible(db, staff, enquiry_id, lock=True)  # 404 if not visible
    db.add(
        EnquiryAssessment(
            enquiry_id=enq.id,
            outcome=payload.outcome.value,
            note=payload.note,
            assessed_by=staff.user.id,
            assessed_at=utcnow(),
        )
    )
    log_activity(
        db,
        "enquiry",
        enq.id,
        "enquiry.assessment_recorded",
        {"outcome": payload.outcome.value},
        ActorType.STAFF,
        actor_user_id=staff.user.id,
    )
    db.commit()
    return ok(_assessments(db, enq.id), "Assessment recorded")


@enquiry.get(
    "/{enquiry_id}/assessment",
    response_model=ApiResponse[list[AssessmentOut]],
    responses=_ERR,
    summary="Assessment history, newest first",
)
def list_assessments(
    enquiry_id: uuid.UUID, staff: AdminDep, db: DbSession, page: PageDep
) -> ApiResponse[list[AssessmentOut]]:
    enq = admin_service.get_visible(db, staff, enquiry_id)
    rows = _assessments(db, enq.id)
    return ok(rows[page.offset : page.offset + page.page_size], meta=page_meta(page, len(rows)))
