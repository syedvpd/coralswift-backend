"""Staff-side communication: reply to an enquirer, upload/replace partner documents for them."""

import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Request, UploadFile
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.common.responses import ApiResponse, ErrorResponse, ok
from app.common.validation import Long, Short
from app.core.config import Settings, get_settings
from app.core.exceptions import AppError
from app.core.protection import rate_limit
from app.database.dependencies import DbSession
from app.modules.admin import service as admin_service
from app.modules.auth.constants import StaffRole
from app.modules.auth.dependencies import PartnerContext, ReviewerDep, StaffContext, require_staff
from app.modules.collaboration import service as collab_service
from app.modules.enquiries.constants import ActorType
from app.modules.enquiries.models import Contact
from app.modules.notifications.constants import NotificationType, TemplateKey
from app.modules.notifications.service import dispatch_notifications, queue_notification
from app.modules.organizations.constants import MembershipRole
from app.modules.partner_documents import service as doc_service
from app.modules.partner_documents.constants import PartnerDocCategory
from app.modules.partner_documents.schemas import DocumentOut, document_out

SettingsDep = Annotated[Settings, Depends(get_settings)]
_ERR: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    413: {"model": ErrorResponse},
    415: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}
AdminDep = Annotated[
    StaffContext,
    Depends(require_staff(StaffRole.SUPER_ADMINISTRATOR, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)),
]
enquiry = APIRouter(prefix="/admin/enquiries", tags=["admin-enquiries"])
documents = APIRouter(prefix="/reviewer/organizations", tags=["reviewer-documents"])


class ReplyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: Short
    body: Long


class ReplyOut(BaseModel):
    queued_to_outbox: bool
    delivery_note: str


@enquiry.post(
    "/{enquiry_id}/reply",
    status_code=201,
    dependencies=[Depends(rate_limit("invite"))],
    response_model=ApiResponse[ReplyOut],
    responses=_ERR,
    summary="Email the requester (outbox; logged as a communication and the first response)",
)
def reply(
    enquiry_id: uuid.UUID,
    payload: ReplyIn,
    request: Request,
    staff: AdminDep,
    db: DbSession,
    settings: SettingsDep,
    background: BackgroundTasks,
) -> ApiResponse[ReplyOut]:
    if not settings.enquiry_reply_enabled:
        raise AppError(
            "Replying to requesters by email is switched off until templates and provider "
            "delivery are approved",
            status_code=409,
            code="FEATURE_DISABLED",
        )
    enq = admin_service.get_visible(db, staff, enquiry_id)  # strategic stays super-admin only
    contact = db.execute(select(Contact).where(Contact.id == enq.contact_id)).scalar_one()
    queue_notification(
        db,
        recipient=contact.business_email,
        kind=NotificationType.REPLY,
        template=TemplateKey.STAFF_REPLY,
        context={
            "name": contact.full_name,
            "subject": payload.subject,
            "body": payload.body,
            "reference": enq.reference_number,
        },
        enquiry_id=enq.id,
        dedupe_key=f"reply:{enq.id}:{uuid.uuid4()}",
    )
    admin_service.add_followup(
        db, staff, enq.id, f"Reply emailed to requester: {payload.subject}", None, "communication"
    )
    background.add_task(
        dispatch_notifications,
        request.app.state.sessionmaker,
        request.app.state.email_sender,
        settings,
    )
    note = (
        "Queued. The console email backend only logs; a real provider is not configured."
        if settings.email_backend == "console"
        else "Queued for delivery by the configured provider."
    )
    return ok(ReplyOut(queued_to_outbox=True, delivery_note=note), "Reply queued")


def _staff_ctx(staff: StaffContext, organization_id: uuid.UUID) -> PartnerContext:
    # Reuses the partner document pipeline (validation, storage, versioning) on the staff
    # member's behalf. The synthetic role is never persisted or exposed.
    return PartnerContext(staff.user, staff.session, organization_id, MembershipRole.MEMBER)


UploadLimit = [Depends(rate_limit("partner-upload", 2))]
FileField = Annotated[UploadFile, File(description="pdf, png, jpg, docx or xlsx")]


@documents.post(
    "/{organization_id}/documents",
    status_code=201,
    dependencies=UploadLimit,
    response_model=ApiResponse[DocumentOut],
    responses=_ERR,
    summary="Upload a document for an organisation (private, quarantined, audited as staff)",
)
def staff_upload(
    request: Request,
    organization_id: uuid.UUID,
    staff: ReviewerDep,
    db: DbSession,
    settings: SettingsDep,
    file: FileField,
    category: Annotated[PartnerDocCategory, Form()],
    expires_on: Annotated[date | None, Form()] = None,
) -> ApiResponse[DocumentOut]:
    org = collab_service.require_org(db, staff, organization_id)
    doc, version = doc_service.upload_new(
        db,
        request.app.state.storage,
        settings,
        _staff_ctx(staff, org.id),
        upload=file,
        category=category,
        expires_on=expires_on,
        actor=ActorType.STAFF,
        action="document.uploaded_by_staff",
    )
    return ok(document_out(doc, version), "Uploaded")


@documents.post(
    "/{organization_id}/documents/{document_id}/versions",
    status_code=201,
    dependencies=UploadLimit,
    response_model=ApiResponse[DocumentOut],
    responses=_ERR,
    summary="Replace a document with a new version (the previous version is kept)",
)
def staff_replace(
    request: Request,
    organization_id: uuid.UUID,
    document_id: uuid.UUID,
    staff: ReviewerDep,
    db: DbSession,
    settings: SettingsDep,
    file: FileField,
    expires_on: Annotated[date | None, Form()] = None,
) -> ApiResponse[DocumentOut]:
    org = collab_service.require_org(db, staff, organization_id)
    doc, version = doc_service.replace(
        db,
        request.app.state.storage,
        settings,
        _staff_ctx(staff, org.id),
        document_id,
        upload=file,
        expires_on=expires_on,
        actor=ActorType.STAFF,
        action="document.replaced_by_staff",
    )
    return ok(document_out(doc, version), "Replaced")
