"""Cross-organisation document queue and read-only policy facts (gap closure: Phase 12, X3, M10).

Reviewers only see documents of organisations whose applications are assigned to them; super
administrators see all. Nothing here changes data."""

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, or_, select

from app.common.pagination import PageDep, page_meta
from app.common.responses import ApiResponse, ErrorResponse, ok
from app.common.utilities import utcnow
from app.common.validation import Long
from app.core.config import Settings, get_settings
from app.core.exceptions import AppError, NotFoundError
from app.database.dependencies import DbSession
from app.integrations.storage import StorageError
from app.modules.admin import lookups
from app.modules.admin import settings_service as cfg
from app.modules.applications.constants import PortalStatus
from app.modules.applications.models import PortalApplication
from app.modules.auth.dependencies import ReviewerDep, SuperAdminDep
from app.modules.auth.security import MAX_PASSWORD_LENGTH
from app.modules.documents.constants import UploadStatus
from app.modules.documents.files import KINDS
from app.modules.documents.scan import ScanStatusMixin
from app.modules.enquiries.activity import log_activity
from app.modules.enquiries.constants import ActorType
from app.modules.organizations.models import PartnerOrganization
from app.modules.partner_documents.constants import DocStatus, PartnerDocCategory, ReviewStatus
from app.modules.partner_documents.models import PartnerDocument, PartnerDocumentVersion

router = APIRouter(prefix="/admin", tags=["admin-reference"])
_ERR: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}
SettingsDep = Annotated[Settings, Depends(get_settings)]


class DocumentQueueRow(ScanStatusMixin):
    document_id: uuid.UUID
    organization_id: uuid.UUID
    organization_name: str
    category: PartnerDocCategory
    status: DocStatus
    version_no: int
    original_filename: str
    content_type: str
    file_size: int
    upload_status: UploadStatus  # quarantined = stored, never scanned
    review_status: ReviewStatus
    review_comment: str | None
    uploaded_at: datetime
    expires_on: date | None
    reviewed_by_name: str | None
    reviewed_at: datetime | None
    retention_date: datetime | None
    retention_until: datetime | None  # same value as retention_date
    purged: bool


class DocumentReviewHistoryRow(BaseModel):
    version_no: int
    review_status: ReviewStatus
    review_comment: str | None
    reviewed_by_name: str | None
    reviewed_at: datetime | None
    uploaded_at: datetime


_SORTS: dict[str, tuple[Any, ...]] = {
    "-uploaded_at": (PartnerDocumentVersion.uploaded_at.desc(), PartnerDocument.id.desc()),
    "uploaded_at": (PartnerDocumentVersion.uploaded_at.asc(), PartnerDocument.id.asc()),
    "expires_on": (PartnerDocumentVersion.expires_on.asc().nulls_last(), PartnerDocument.id.asc()),
}


@router.get(
    "/documents",
    response_model=ApiResponse[list[DocumentQueueRow]],
    responses=_ERR,
    summary="Partner documents across organisations (current version of each)",
)
def document_queue(
    staff: ReviewerDep,
    db: DbSession,
    page: PageDep,
    organization_id: Annotated[uuid.UUID | None, Query()] = None,
    category: Annotated[PartnerDocCategory | None, Query()] = None,
    review_status: Annotated[ReviewStatus | None, Query()] = None,
    upload_status: Annotated[UploadStatus | None, Query()] = None,
    status: Annotated[DocStatus | None, Query()] = None,
    expires_before: Annotated[date | None, Query()] = None,
    uploaded_from: Annotated[datetime | None, Query()] = None,
    uploaded_to: Annotated[datetime | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=100, description="organisation or filename")] = None,
    sort: Annotated[Literal["-uploaded_at", "uploaded_at", "expires_on"], Query()] = "-uploaded_at",
) -> ApiResponse[list[DocumentQueueRow]]:
    stmt = (
        select(PartnerDocument, PartnerDocumentVersion, PartnerOrganization.legal_name)
        .join(
            PartnerDocumentVersion,
            (PartnerDocumentVersion.document_id == PartnerDocument.id)
            & (PartnerDocumentVersion.version_no == PartnerDocument.current_version_no),
        )
        .join(PartnerOrganization, PartnerOrganization.id == PartnerDocument.organization_id)
    )

    if not staff.is_super_admin:  # reviewers: only organisations whose application is theirs
        stmt = stmt.where(
            PartnerDocument.organization_id.in_(
                select(PortalApplication.organization_id).where(
                    PortalApplication.assigned_reviewer_id == staff.user.id,
                    PortalApplication.status != PortalStatus.DRAFT,
                )
            )
        )
    if organization_id:
        stmt = stmt.where(PartnerDocument.organization_id == organization_id)
    if category:
        stmt = stmt.where(PartnerDocument.category == category)
    if status:
        stmt = stmt.where(PartnerDocument.status == status)
    if review_status:
        stmt = stmt.where(PartnerDocumentVersion.review_status == review_status)
    if upload_status:
        stmt = stmt.where(PartnerDocumentVersion.upload_status == upload_status)
    if expires_before:
        stmt = stmt.where(PartnerDocumentVersion.expires_on <= expires_before)
    if uploaded_from:
        stmt = stmt.where(PartnerDocumentVersion.uploaded_at >= uploaded_from)
    if uploaded_to:
        stmt = stmt.where(PartnerDocumentVersion.uploaded_at < uploaded_to)
    if q:
        like = "%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        stmt = stmt.where(
            or_(
                PartnerOrganization.legal_name.ilike(like, escape="\\"),
                PartnerDocumentVersion.original_filename.ilike(like, escape="\\"),
            )
        )
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(stmt.order_by(*_SORTS[sort]).limit(page.page_size).offset(page.offset)).all()
    names = lookups.user_names(db, (v.reviewed_by for _, v, _ in rows))
    return ok(
        [
            DocumentQueueRow(
                document_id=d.id,
                organization_id=d.organization_id,
                organization_name=org,
                category=d.category,
                status=d.status,
                version_no=v.version_no,
                original_filename=v.original_filename,
                content_type=v.content_type,
                file_size=v.file_size,
                upload_status=v.upload_status,
                review_status=v.review_status,
                review_comment=v.review_comment,
                uploaded_at=v.uploaded_at,
                expires_on=v.expires_on,
                reviewed_by_name=names.get(v.reviewed_by) if v.reviewed_by else None,
                reviewed_at=v.reviewed_at,
                retention_date=v.retention_date,
                retention_until=v.retention_date,
                purged=v.purged_at is not None,
            )
            for d, v, org in rows
        ],
        meta=page_meta(page, total),
    )


@router.get(
    "/documents/{document_id}/history",
    response_model=ApiResponse[list[DocumentReviewHistoryRow]],
    responses={**_ERR, 404: {"model": ErrorResponse}},
    summary="Document versions and their staff review outcomes",
)
def document_review_history(
    document_id: uuid.UUID, staff: ReviewerDep, db: DbSession, page: PageDep
) -> ApiResponse[list[DocumentReviewHistoryRow]]:
    document = db.get(PartnerDocument, document_id)
    if document is None:
        raise NotFoundError("Document not found")
    if not staff.is_super_admin:
        assigned = db.execute(
            select(PortalApplication.id)
            .where(
                PortalApplication.organization_id == document.organization_id,
                PortalApplication.assigned_reviewer_id == staff.user.id,
                PortalApplication.status != PortalStatus.DRAFT,
            )
            .limit(1)
        ).first()
        if assigned is None:
            raise NotFoundError("Document not found")
    version_stmt = select(PartnerDocumentVersion).where(
        PartnerDocumentVersion.document_id == document.id
    )
    total = db.execute(select(func.count()).select_from(version_stmt.subquery())).scalar_one()
    versions = list(
        db.execute(
            version_stmt.order_by(PartnerDocumentVersion.version_no.desc())
            .limit(page.page_size)
            .offset(page.offset)
        ).scalars()
    )
    names = lookups.user_names(db, (v.reviewed_by for v in versions if v.reviewed_by))
    return ok(
        [
            DocumentReviewHistoryRow(
                version_no=v.version_no,
                review_status=v.review_status,
                review_comment=v.review_comment,
                reviewed_by_name=names.get(v.reviewed_by) if v.reviewed_by else None,
                reviewed_at=v.reviewed_at,
                uploaded_at=v.uploaded_at,
            )
            for v in versions
        ],
        meta=page_meta(page, total),
    )


# ----------------------------------------------------------------- security policy
class SecurityPolicyOut(BaseModel):
    """Read-only effective policy. Values come from deployment configuration, never secrets."""

    password_min_length: int
    password_rules: str
    staff_mfa_required: bool
    partner_mfa: Literal["optional"]
    login_max_failures: int
    login_lockout_minutes: int
    access_token_minutes: int
    refresh_token_minutes: int
    invitation_ttl_hours: int
    password_reset_ttl_minutes: int
    rate_limit_per_minute: int
    max_request_body_bytes: int
    max_upload_bytes: int
    max_documents_per_enquiry: int
    allowed_upload_types: list[str]
    malware_scanning: Literal["none: uploads stay quarantined"]
    invitation_link_path: str
    reset_link_path: str
    captcha_enabled: bool


@router.get(
    "/security-policy",
    response_model=ApiResponse[SecurityPolicyOut],
    responses=_ERR,
    summary="Effective password, session, MFA, rate-limit and upload policy (read-only)",
)
def security_policy(staff: SuperAdminDep, settings: SettingsDep) -> ApiResponse[SecurityPolicyOut]:
    return ok(
        SecurityPolicyOut(
            password_min_length=settings.password_min_length,
            password_rules=(
                f"{settings.password_min_length}-{MAX_PASSWORD_LENGTH} characters; "
                "must not equal the email address"
            ),
            staff_mfa_required=settings.staff_mfa_required,
            partner_mfa="optional",
            login_max_failures=settings.login_max_failures,
            login_lockout_minutes=settings.login_lockout_minutes,
            access_token_minutes=settings.access_token_expire_minutes,
            refresh_token_minutes=settings.refresh_token_expire_minutes,
            invitation_ttl_hours=settings.invitation_ttl_hours,
            password_reset_ttl_minutes=settings.password_reset_ttl_minutes,
            rate_limit_per_minute=settings.rate_limit_per_minute,
            max_request_body_bytes=settings.max_request_body_bytes,
            max_upload_bytes=settings.max_upload_bytes,
            max_documents_per_enquiry=settings.max_documents_per_enquiry,
            allowed_upload_types=sorted(KINDS),
            malware_scanning="none: uploads stay quarantined",
            invitation_link_path="/activate?token=",
            reset_link_path="/reset-password?token=",
            captcha_enabled=settings.captcha_enabled,
        )
    )


# ------------------------------------------------------------ hard deletion
class PurgeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Long


class PurgeOut(BaseModel):
    document_id: uuid.UUID
    versions_purged: int


@router.post(
    "/documents/{document_id}/purge",
    response_model=ApiResponse[PurgeOut],
    responses={**_ERR, 404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    summary="Permanently delete the stored files of a removed document (rows stay for audit)",
)
def purge_document(
    document_id: uuid.UUID,
    payload: PurgeIn,
    request: Request,
    staff: SuperAdminDep,
    db: DbSession,
) -> ApiResponse[PurgeOut]:
    """Irreversible. Only for documents the partner removed whose every version has a retention
    date in the past; the retention period itself is an owner decision (D4)."""
    if cfg.get_int(db, "retention.partner_document_days") is None:
        raise AppError(
            "Permanent deletion is blocked: the retention policy has not been approved. "
            "Set retention.partner_document_days only after legal sign-off.",
            status_code=409,
            code="RETENTION_POLICY_NOT_APPROVED",
        )
    doc = db.execute(
        select(PartnerDocument).where(PartnerDocument.id == document_id).with_for_update()
    ).scalar_one_or_none()
    if doc is None:
        raise NotFoundError("Document not found")
    if doc.status is not DocStatus.REMOVED:
        raise AppError("Only removed documents can be purged", status_code=409, code="NOT_REMOVED")
    versions = list(
        db.execute(
            select(PartnerDocumentVersion)
            .where(PartnerDocumentVersion.document_id == doc.id)
            .with_for_update()
        ).scalars()
    )
    now = utcnow()
    if any(v.retention_date is None or v.retention_date > now for v in versions):
        raise AppError(
            "Retention period has not ended for every version",
            status_code=409,
            code="RETENTION_ACTIVE",
        )
    purged = 0
    for v in versions:
        if v.purged_at is not None:
            continue
        try:
            request.app.state.storage.delete(v.storage_key)
        except StorageError:
            raise AppError(
                "File storage is unavailable", status_code=503, code="STORAGE_UNAVAILABLE"
            ) from None
        v.purged_at = now
        purged += 1
    log_activity(
        db,
        "partner_document",
        doc.id,
        "document.purged_by_staff",
        {"versions": purged},
        ActorType.STAFF,
        actor_user_id=staff.user.id,
        organization_id=doc.organization_id,
    )
    db.commit()
    return ok(PurgeOut(document_id=doc.id, versions_purged=purged), "Files deleted")
