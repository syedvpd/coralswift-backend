"""Onboarding record and checklist. Staff create records and tasks; partners see visible tasks."""

import json
import uuid
from datetime import date, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.pagination import PageDep, page_meta
from app.common.responses import ApiResponse, ErrorResponse, ok
from app.common.utilities import utcnow
from app.common.validation import Long, Short
from app.core.exceptions import AppError, NotFoundError
from app.database.dependencies import DbSession
from app.modules.admin import settings_service as cfg
from app.modules.applications.models import ApplicationStatusHistory, PortalApplication
from app.modules.auth.dependencies import (
    CollabReadDep,
    PartnerDep,
    ReviewerDep,
    StaffContext,
    SuperAdminDep,
)
from app.modules.auth.models import AuthSession
from app.modules.collaboration import service as collab_service
from app.modules.enquiries.activity import log_activity
from app.modules.enquiries.constants import ActorType
from app.modules.onboarding.models import OnboardingRecord, OnboardingTask, TaskStatus
from app.modules.organizations.constants import MembershipStatus
from app.modules.organizations.models import PartnerMembership, PartnerOrganization
from app.modules.partner_documents.constants import PartnerDocCategory

_ERR: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}
partner = APIRouter(prefix="/partner/onboarding", tags=["partner-onboarding"])
staff_router = APIRouter(prefix="/reviewer/onboarding", tags=["reviewer-onboarding"])
template_router = APIRouter(prefix="/admin/onboarding-template", tags=["admin-onboarding"])


class TaskOut(BaseModel):
    id: uuid.UUID
    name: str
    status: TaskStatus
    required_action: str | None
    due_date: date | None
    completed_at: datetime | None
    document_category: PartnerDocCategory | None
    is_overdue: bool


class StageOut(BaseModel):
    stage: str
    entered_at: datetime


class OnboardingOut(BaseModel):
    id: uuid.UUID
    reference: str
    application_id: uuid.UUID | None
    started_at: datetime
    completed_at: datetime | None
    provisioned_at: datetime
    first_login_at: datetime | None
    stages: list[StageOut]
    tasks: list[TaskOut]
    progress: dict[str, int]


class StaffOnboardingOut(OnboardingOut):
    organization_id: uuid.UUID
    organization_name: str


class RecordIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization_id: uuid.UUID
    application_id: uuid.UUID | None = None
    use_template: bool = False  # copy the editable `onboarding.template` setting (D10)


class TaskIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Short
    required_action: Long | None = None
    due_date: date | None = None
    document_category: PartnerDocCategory | None = None
    partner_visible: bool = True


class TaskUpdate(BaseModel):
    """Omitted = unchanged; null clears nullable fields."""

    model_config = ConfigDict(extra="forbid")

    name: Short | None = None
    required_action: Long | None = None
    due_date: date | None = None
    document_category: PartnerDocCategory | None = None
    partner_visible: bool | None = None
    status: TaskStatus | None = None


def _task_out(t: OnboardingTask) -> TaskOut:
    overdue = (
        t.status is not TaskStatus.COMPLETED
        and t.due_date is not None
        and t.due_date < utcnow().date()
    )
    return TaskOut(
        id=t.id,
        name=t.name,
        status=t.status,
        required_action=t.required_action,
        due_date=t.due_date,
        completed_at=t.completed_at,
        document_category=t.document_category,
        is_overdue=overdue,
    )


def _build(db: Session, rec: OnboardingRecord, *, partner_view: bool) -> dict[str, Any]:
    stmt = select(OnboardingTask).where(OnboardingTask.record_id == rec.id)
    if partner_view:
        stmt = stmt.where(OnboardingTask.partner_visible.is_(True))
    tasks = list(
        db.execute(stmt.order_by(OnboardingTask.position, OnboardingTask.created_at)).scalars()
    )
    stages: list[StageOut] = []
    if rec.application_id:
        hist = db.execute(
            select(ApplicationStatusHistory)
            .where(ApplicationStatusHistory.application_id == rec.application_id)
            .order_by(ApplicationStatusHistory.created_at)
        ).scalars()
        stages = [StageOut(stage=h.to_status.value, entered_at=h.created_at) for h in hist]
    first_login = db.execute(
        select(func.min(AuthSession.created_at))
        .join(PartnerMembership, PartnerMembership.user_id == AuthSession.user_id)
        .where(
            PartnerMembership.organization_id == rec.organization_id,
            PartnerMembership.status == MembershipStatus.ACTIVE,
        )
    ).scalar_one()
    done = sum(1 for t in tasks if t.status is TaskStatus.COMPLETED)
    return {
        "id": rec.id,
        "reference": rec.reference,
        "application_id": rec.application_id,
        "started_at": rec.started_at,
        "completed_at": rec.completed_at,
        "provisioned_at": rec.created_at,
        "first_login_at": first_login,
        "stages": stages,
        "tasks": [_task_out(t) for t in tasks],
        "progress": {"total": len(tasks), "completed": done},
    }


@partner.get(
    "",
    response_model=ApiResponse[OnboardingOut | None],
    responses=_ERR,
    summary="Your onboarding file with the visible checklist (null until staff start one)",
)
def my_onboarding(ctx: PartnerDep, db: DbSession) -> ApiResponse[OnboardingOut | None]:
    rec = db.execute(
        select(OnboardingRecord).where(OnboardingRecord.organization_id == ctx.organization_id)
    ).scalar_one_or_none()
    return ok(OnboardingOut(**_build(db, rec, partner_view=True)) if rec else None)


def _record(
    db: Session, staff: StaffContext, record_id: uuid.UUID, lock: bool = False
) -> OnboardingRecord:
    stmt = select(OnboardingRecord).where(
        OnboardingRecord.id == record_id,
        collab_service.org_scope(staff, OnboardingRecord.organization_id),
    )
    rec = db.execute(stmt.with_for_update() if lock else stmt).scalar_one_or_none()
    if rec is None:
        raise NotFoundError("Onboarding record not found")
    return rec


def _staff_out(db: Session, rec: OnboardingRecord) -> StaffOnboardingOut:
    org = db.get(PartnerOrganization, rec.organization_id)
    return StaffOnboardingOut(
        **_build(db, rec, partner_view=False),
        organization_id=rec.organization_id,
        organization_name=org.legal_name if org else "",
    )


def _apply_template(db: Session, rec: OnboardingRecord) -> None:
    raw = cfg.get(db, "onboarding.template")
    for i, t in enumerate(json.loads(raw) if raw else []):
        days = t.get("due_in_days")
        db.add(
            OnboardingTask(
                record_id=rec.id,
                name=t["name"],
                required_action=t.get("required_action"),
                due_date=(rec.started_at + timedelta(days=days)).date()
                if days is not None
                else None,
                document_category=t.get("document_category"),
                position=i,
            )
        )


class TemplateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tasks: list[dict[str, Any]]


@template_router.get(
    "", response_model=ApiResponse[list[dict[str, Any]]], responses=_ERR,
    summary="Editable initial onboarding task template (empty until staff define it)",
)  # fmt: skip
def get_template(staff: ReviewerDep, db: DbSession) -> ApiResponse[list[dict[str, Any]]]:
    raw = cfg.get(db, "onboarding.template")
    return ok(json.loads(raw) if raw else [])


@template_router.put(
    "", response_model=ApiResponse[list[dict[str, Any]]], responses=_ERR,
    summary="Replace the onboarding template (super administrator)",
)  # fmt: skip
def put_template(
    payload: TemplateIn, staff: SuperAdminDep, db: DbSession
) -> ApiResponse[list[dict[str, Any]]]:
    value = cfg.put(db, "onboarding.template", json.dumps(payload.tasks), staff.user.id)
    log_activity(
        db, "setting", uuid.uuid5(uuid.NAMESPACE_URL, "onboarding.template"),
        "admin.setting_changed", {"key": "onboarding.template"}, ActorType.STAFF,
        actor_user_id=staff.user.id,
    )  # fmt: skip
    db.commit()
    return ok(json.loads(value))


@staff_router.post(
    "",
    status_code=201,
    response_model=ApiResponse[StaffOnboardingOut],
    responses=_ERR,
    summary="Start the onboarding file of an organisation (one per organisation)",
)
def create_record(
    payload: RecordIn, staff: ReviewerDep, db: DbSession
) -> ApiResponse[StaffOnboardingOut]:
    org = collab_service.require_org(db, staff, payload.organization_id)
    if payload.application_id is not None:
        owned = db.execute(
            select(PortalApplication.id).where(
                PortalApplication.id == payload.application_id,
                PortalApplication.organization_id == org.id,
            )
        ).first()
        if owned is None:
            raise NotFoundError("Application not found")
    if db.execute(
        select(OnboardingRecord.id).where(OnboardingRecord.organization_id == org.id)
    ).first():
        raise AppError("Onboarding already started", status_code=409, code="ALREADY_EXISTS")
    rec = OnboardingRecord(
        reference=collab_service.reference("ONB"),
        organization_id=org.id,
        application_id=payload.application_id,
        started_at=utcnow(),
        created_by=staff.user.id,
    )
    db.add(rec)
    db.flush()
    if payload.use_template:
        _apply_template(db, rec)
    log_activity(
        db, "onboarding", rec.id, "onboarding.started", None, ActorType.STAFF,
        actor_user_id=staff.user.id, organization_id=org.id,
    )  # fmt: skip
    db.commit()
    db.refresh(rec)
    return ok(_staff_out(db, rec), "Onboarding started")


@staff_router.get("", response_model=ApiResponse[list[StaffOnboardingOut]], responses=_ERR)
def list_records(
    staff: CollabReadDep,
    db: DbSession,
    page: PageDep,
    organization_id: Annotated[uuid.UUID | None, Query()] = None,
    completed: Annotated[bool | None, Query()] = None,
) -> ApiResponse[list[StaffOnboardingOut]]:
    stmt = select(OnboardingRecord).where(
        collab_service.org_scope(staff, OnboardingRecord.organization_id)
    )
    if organization_id:
        stmt = stmt.where(OnboardingRecord.organization_id == organization_id)
    if completed is not None:
        stmt = stmt.where(
            OnboardingRecord.completed_at.is_not(None)
            if completed
            else OnboardingRecord.completed_at.is_(None)
        )
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(
        stmt.order_by(OnboardingRecord.started_at.desc(), OnboardingRecord.id)
        .limit(page.page_size)
        .offset(page.offset)
    ).scalars()
    return ok([_staff_out(db, r) for r in rows], meta=page_meta(page, total))


@staff_router.get("/{record_id}", response_model=ApiResponse[StaffOnboardingOut], responses=_ERR)
def get_record(
    record_id: uuid.UUID, staff: CollabReadDep, db: DbSession
) -> ApiResponse[StaffOnboardingOut]:
    return ok(_staff_out(db, _record(db, staff, record_id)))


@staff_router.post(
    "/{record_id}/tasks",
    status_code=201,
    response_model=ApiResponse[StaffOnboardingOut],
    responses=_ERR,
    summary="Add a checklist task (name, action, due date, linked document category)",
)
def add_task(
    record_id: uuid.UUID, payload: TaskIn, staff: ReviewerDep, db: DbSession
) -> ApiResponse[StaffOnboardingOut]:
    rec = _record(db, staff, record_id, lock=True)
    position = db.execute(
        select(func.count()).select_from(OnboardingTask).where(OnboardingTask.record_id == rec.id)
    ).scalar_one()
    db.add(
        OnboardingTask(
            record_id=rec.id,
            name=payload.name,
            required_action=payload.required_action,
            due_date=payload.due_date,
            document_category=payload.document_category,
            partner_visible=payload.partner_visible,
            position=position,
        )
    )
    rec.completed_at = None  # a new open task reopens the file
    log_activity(
        db, "onboarding", rec.id, "onboarding.task_added", None, ActorType.STAFF,
        actor_user_id=staff.user.id, organization_id=rec.organization_id,
    )  # fmt: skip
    db.commit()
    db.refresh(rec)
    return ok(_staff_out(db, rec))


@staff_router.patch(
    "/{record_id}/tasks/{task_id}",
    response_model=ApiResponse[StaffOnboardingOut],
    responses=_ERR,
    summary="Edit a task; status completed records the completion time",
)
def update_task(
    record_id: uuid.UUID,
    task_id: uuid.UUID,
    payload: TaskUpdate,
    staff: ReviewerDep,
    db: DbSession,
) -> ApiResponse[StaffOnboardingOut]:
    rec = _record(db, staff, record_id, lock=True)
    task = db.execute(
        select(OnboardingTask).where(
            OnboardingTask.id == task_id, OnboardingTask.record_id == rec.id
        )
    ).scalar_one_or_none()
    if task is None:
        raise NotFoundError("Task not found")
    changes = payload.model_dump(exclude_unset=True)
    for required in ("name", "status", "partner_visible"):
        if required in changes and changes[required] is None:
            raise AppError(f"{required} cannot be cleared", status_code=422, code="REQUIRED_FIELD")
    for field, value in changes.items():
        setattr(task, field, value)
    if "status" in changes:
        task.completed_at = utcnow() if task.status is TaskStatus.COMPLETED else None
    log_activity(
        db, "onboarding", rec.id, "onboarding.task_updated", {"fields": sorted(changes)},
        ActorType.STAFF, actor_user_id=staff.user.id, organization_id=rec.organization_id,
    )  # fmt: skip
    db.commit()
    db.refresh(rec)
    return ok(_staff_out(db, rec))


@staff_router.post(
    "/{record_id}/complete",
    response_model=ApiResponse[StaffOnboardingOut],
    responses=_ERR,
    summary="Close the onboarding file (409 while a task is still open)",
)
def complete_record(
    record_id: uuid.UUID, staff: ReviewerDep, db: DbSession
) -> ApiResponse[StaffOnboardingOut]:
    rec = _record(db, staff, record_id, lock=True)
    open_tasks = db.execute(
        select(func.count())
        .select_from(OnboardingTask)
        .where(OnboardingTask.record_id == rec.id, OnboardingTask.status != TaskStatus.COMPLETED)
    ).scalar_one()
    if open_tasks:
        raise AppError(f"{open_tasks} task(s) still open", status_code=409, code="TASKS_OPEN")
    if rec.completed_at is None:
        rec.completed_at = utcnow()
        log_activity(
            db, "onboarding", rec.id, "onboarding.completed", None, ActorType.STAFF,
            actor_user_id=staff.user.id, organization_id=rec.organization_id,
        )  # fmt: skip
    db.commit()
    db.refresh(rec)
    return ok(_staff_out(db, rec), "Onboarding completed")
