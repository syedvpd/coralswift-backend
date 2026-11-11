"""Public content API (/content) and content-admin API (/admin/content)."""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.common.pagination import PageDep, page_meta
from app.common.responses import ApiResponse, ErrorResponse, ok
from app.common.validation import Long, Short
from app.core.config import Settings, get_settings
from app.core.protection import rate_limit
from app.database.dependencies import DbSession
from app.modules.auth.constants import StaffRole
from app.modules.auth.dependencies import StaffContext, SuperAdminDep, require_staff
from app.modules.content import service
from app.modules.content.constants import ClaimCategory, ClaimStatus, ContentStatus, ContentType
from app.modules.content.models import ContentItem

public = APIRouter(prefix="/content", tags=["content"])
admin = APIRouter(prefix="/admin/content", tags=["admin-content"])
ContentAdminDep = Annotated[
    StaffContext,
    Depends(require_staff(StaffRole.CONTENT_ADMINISTRATOR, StaffRole.SUPER_ADMINISTRATOR)),
]
SettingsDep = Annotated[Settings, Depends(get_settings)]
_ERR: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}
Slug = Annotated[str, Field(min_length=2, max_length=120, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")]
Tags = Annotated[
    list[Annotated[str, Field(min_length=1, max_length=40, pattern=r"^[a-z0-9-]+$")]],
    Field(max_length=15),
]


HttpsUrl = Annotated[str, Field(max_length=500, pattern=r"^https://[^\s<>\"']+$")]
SEO_FIELDS = (
    "seo_title",
    "seo_description",
    "canonical_url",
    "og_title",
    "og_description",
    "og_image_url",
    "image_url",
    "image_alt",
)


class SeoFields(BaseModel):
    """Optional SEO / social / cover-image metadata. URLs must be https; send null to clear."""

    seo_title: Annotated[str, Field(max_length=200)] | None = None
    seo_description: Annotated[str, Field(max_length=300)] | None = None
    canonical_url: HttpsUrl | None = None
    og_title: Annotated[str, Field(max_length=200)] | None = None
    og_description: Annotated[str, Field(max_length=300)] | None = None
    og_image_url: HttpsUrl | None = None
    image_url: HttpsUrl | None = None
    image_alt: Annotated[str, Field(max_length=200)] | None = None


class ContentIn(SeoFields):
    model_config = ConfigDict(extra="forbid")

    slug: Slug
    content_type: ContentType
    title: Short
    summary: Annotated[str, Field(max_length=500)] | None = None
    body: Annotated[str, Field(min_length=1, max_length=100_000)]
    category: Annotated[str, Field(max_length=80)] | None = None
    tags: Tags = Field(default_factory=list)
    claim_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)


class ContentUpdate(SeoFields):
    model_config = ConfigDict(extra="forbid")

    title: Short | None = None
    summary: Annotated[str, Field(max_length=500)] | None = None
    body: Annotated[str, Field(min_length=1, max_length=100_000)] | None = None
    category: Annotated[str, Field(max_length=80)] | None = None
    tags: Tags | None = None
    claim_ids: list[uuid.UUID] | None = Field(default=None, max_length=50)


class NoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: Long


class OptionalNoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: Long | None = None


class ScheduleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    publish_at: datetime

    @field_validator("publish_at")
    @classmethod
    def require_future_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("publish_at must include a timezone")
        if value <= datetime.now(UTC):
            raise ValueError("publish_at must be in the future")
        return value


class AttachmentOut(BaseModel):
    filename: str
    content_type: str | None
    size: int | None
    version_label: str | None


class PublicContent(SeoFields):
    slug: str
    content_type: ContentType
    title: str
    summary: str | None
    category: str | None
    tags: list[str]
    published_at: datetime | None
    last_reviewed_at: datetime | None
    attachment: AttachmentOut | None


class PublicContentDetail(PublicContent):
    body: str
    related: list[PublicContent]


class AdminContent(PublicContent):
    id: uuid.UUID
    status: ContentStatus
    body: str
    owner_id: uuid.UUID
    reviewer_id: uuid.UUID | None
    review_note: str | None
    current_version: int
    claim_ids: list[str]
    scheduled_publish_at: datetime | None = None


class VersionOut(BaseModel):
    version_no: int
    title: str
    summary: str | None
    body: str
    edited_by: uuid.UUID
    created_at: datetime


def _pub(i: ContentItem) -> PublicContent:
    att = (
        AttachmentOut(
            filename=i.attachment_filename or "",
            content_type=i.attachment_content_type,
            size=i.attachment_size,
            version_label=i.version_label,
        )
        if i.attachment_key
        else None
    )
    return PublicContent(
        slug=i.slug,
        content_type=i.content_type,
        title=i.title,
        summary=i.summary,
        category=i.category,
        tags=i.tags or [],
        published_at=i.published_at,
        last_reviewed_at=i.last_reviewed_at,
        attachment=att,
        **{k: getattr(i, k) for k in SEO_FIELDS},
    )


def _adm(i: ContentItem) -> AdminContent:
    return AdminContent(
        **_pub(i).model_dump(),
        id=i.id,
        status=i.status,
        body=i.body,
        owner_id=i.owner_id,
        reviewer_id=i.reviewer_id,
        review_note=i.review_note,
        current_version=i.current_version,
        claim_ids=list(i.claim_ids or []),
        scheduled_publish_at=i.scheduled_publish_at,
    )


def _cache(response: Response) -> None:
    response.headers["Cache-Control"] = "public, max-age=300"


# ------------------------------------------------------------------ public
@public.get(
    "",
    response_model=ApiResponse[list[PublicContent]],
    summary="Published content: search, filter by type/category/tag",
)
def list_public(
    response: Response,
    db: DbSession,
    page: PageDep,
    q: Annotated[str | None, Query(max_length=100)] = None,
    type: Annotated[ContentType | None, Query()] = None,
    category: Annotated[str | None, Query(max_length=80)] = None,
    tag: Annotated[str | None, Query(max_length=40)] = None,
) -> ApiResponse[list[PublicContent]]:  # noqa: A002
    _cache(response)
    items, total = service.search_published(
        db, page.page_size, page.offset, q=q, content_type=type, category=category, tag=tag
    )
    return ok([_pub(i) for i in items], meta=page_meta(page, total))


class SitemapEntry(BaseModel):
    slug: str
    updated_at: datetime


@public.get(
    "/sitemap",
    response_model=ApiResponse[list[SitemapEntry]],
    summary="Slugs and last-modified times of published content (SEO)",
)
def sitemap(response: Response, db: DbSession) -> ApiResponse[list[SitemapEntry]]:
    _cache(response)
    return ok([SitemapEntry(slug=s, updated_at=u) for s, u in service.sitemap(db)])


@public.get("/{slug}", response_model=ApiResponse[PublicContentDetail], responses=_ERR)
def get_public(slug: str, response: Response, db: DbSession) -> ApiResponse[PublicContentDetail]:
    _cache(response)
    item = service.get_published(db, slug)
    return ok(
        PublicContentDetail(
            **_pub(item).model_dump(),
            body=item.body,
            related=[_pub(r) for r in service.related(db, item)],
        )
    )


@public.get(
    "/{slug}/download",
    responses={**_ERR, 200: {"content": {"application/octet-stream": {}}}},
    dependencies=[Depends(rate_limit("content-download", 3))],
    summary="Download the attachment of published content",
)
def download(slug: str, request: Request, db: DbSession) -> Response:
    data, item = service.read_attachment(db, request.app.state.storage, slug)
    return Response(
        content=data,
        media_type=item.attachment_content_type or "application/octet-stream",
        headers={
            "Content-Disposition": 'attachment; filename="document"',
            "Cache-Control": "public, max-age=300",
        },
    )


# ------------------------------------------------------------------- admin
@admin.post(
    "",
    status_code=201,
    response_model=ApiResponse[AdminContent],
    responses=_ERR,
    summary="Create a draft",
)
def create(payload: ContentIn, staff: ContentAdminDep, db: DbSession) -> ApiResponse[AdminContent]:
    return ok(_adm(service.create(db, staff, payload.model_dump(mode="json"))))


@admin.get("", response_model=ApiResponse[list[AdminContent]], responses=_ERR)
def list_admin(
    staff: ContentAdminDep,
    db: DbSession,
    page: PageDep,
    status: Annotated[ContentStatus | None, Query()] = None,
    type: Annotated[ContentType | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    updated_from: Annotated[datetime | None, Query()] = None,
    updated_to: Annotated[datetime | None, Query()] = None,
    sort: Annotated[
        Literal["-updated_at", "updated_at", "-created_at", "title"], Query()
    ] = "-updated_at",
) -> ApiResponse[list[AdminContent]]:  # noqa: A002
    items, total = service.list_admin(
        db,
        page.page_size,
        page.offset,
        status,
        type,
        q,
        updated_from=updated_from,
        updated_to=updated_to,
        sort=sort,
    )
    return ok([_adm(i) for i in items], meta=page_meta(page, total))


@admin.get("/{item_id}", response_model=ApiResponse[AdminContent], responses=_ERR)
def get_one(item_id: uuid.UUID, staff: ContentAdminDep, db: DbSession) -> ApiResponse[AdminContent]:
    return ok(_adm(service.get_item(db, item_id)))


@admin.patch(
    "/{item_id}",
    response_model=ApiResponse[AdminContent],
    responses=_ERR,
    summary="Edit a draft (stores a new version)",
)
def update(
    item_id: uuid.UUID, payload: ContentUpdate, staff: ContentAdminDep, db: DbSession
) -> ApiResponse[AdminContent]:
    return ok(
        _adm(
            service.update(
                db,
                staff,
                item_id,
                {
                    k: v
                    for k, v in payload.model_dump(mode="json", exclude_unset=True).items()
                    if v is not None or k in SEO_FIELDS  # null clears an SEO field only
                },
            )
        )
    )


@admin.get("/{item_id}/versions", response_model=ApiResponse[list[VersionOut]], responses=_ERR)
def versions(
    item_id: uuid.UUID, staff: ContentAdminDep, db: DbSession
) -> ApiResponse[list[VersionOut]]:
    service.get_item(db, item_id)
    return ok(
        [
            VersionOut(
                version_no=v.version_no,
                title=v.title,
                summary=v.summary,
                body=v.body,
                edited_by=v.edited_by,
                created_at=v.created_at,
            )
            for v in service.versions(db, item_id)
        ]
    )


@admin.post(
    "/{item_id}/submit",
    response_model=ApiResponse[AdminContent],
    responses=_ERR,
    summary="draft -> in_review",
)
def submit(item_id: uuid.UUID, staff: ContentAdminDep, db: DbSession) -> ApiResponse[AdminContent]:
    return ok(_adm(service.submit_for_review(db, staff, item_id)))


@admin.post(
    "/{item_id}/approve",
    response_model=ApiResponse[AdminContent],
    responses=_ERR,
    summary="in_review -> approved (super administrator)",
)
def approve(
    item_id: uuid.UUID, payload: OptionalNoteIn, staff: SuperAdminDep, db: DbSession
) -> ApiResponse[AdminContent]:
    return ok(_adm(service.approve(db, staff, item_id, payload.note)))


@admin.post(
    "/{item_id}/reject",
    response_model=ApiResponse[AdminContent],
    responses=_ERR,
    summary="in_review -> draft with a note (super administrator)",
)
def reject(
    item_id: uuid.UUID, payload: NoteIn, staff: SuperAdminDep, db: DbSession
) -> ApiResponse[AdminContent]:
    return ok(_adm(service.reject(db, staff, item_id, payload.note)))


@admin.post(
    "/{item_id}/publish",
    response_model=ApiResponse[AdminContent],
    responses=_ERR,
    summary="approved -> published",
)
def publish(item_id: uuid.UUID, staff: ContentAdminDep, db: DbSession) -> ApiResponse[AdminContent]:
    return ok(_adm(service.publish(db, staff, item_id)))


@admin.post(
    "/{item_id}/schedule",
    response_model=ApiResponse[AdminContent],
    responses=_ERR,
    summary="Schedule approved, claims-cleared content for future publication",
)
def schedule_publish(
    item_id: uuid.UUID, payload: ScheduleIn, staff: ContentAdminDep, db: DbSession
) -> ApiResponse[AdminContent]:
    return ok(_adm(service.schedule_publish(db, staff, item_id, payload.publish_at)))


@admin.delete(
    "/{item_id}/schedule",
    response_model=ApiResponse[AdminContent],
    responses=_ERR,
    summary="Cancel a scheduled publication",
)
def cancel_scheduled_publish(
    item_id: uuid.UUID, staff: ContentAdminDep, db: DbSession
) -> ApiResponse[AdminContent]:
    return ok(_adm(service.cancel_scheduled_publish(db, staff, item_id)))


@admin.post("/{item_id}/unpublish", response_model=ApiResponse[AdminContent], responses=_ERR)
def unpublish(
    item_id: uuid.UUID, staff: ContentAdminDep, db: DbSession
) -> ApiResponse[AdminContent]:
    return ok(_adm(service.unpublish(db, staff, item_id)))


@admin.post(
    "/{item_id}/reopen",
    response_model=ApiResponse[AdminContent],
    responses=_ERR,
    summary="Back to draft for editing (removes it from the site)",
)
def reopen(item_id: uuid.UUID, staff: ContentAdminDep, db: DbSession) -> ApiResponse[AdminContent]:
    return ok(_adm(service.reopen(db, staff, item_id)))


@admin.post("/{item_id}/archive", response_model=ApiResponse[AdminContent], responses=_ERR)
def archive(item_id: uuid.UUID, staff: ContentAdminDep, db: DbSession) -> ApiResponse[AdminContent]:
    return ok(_adm(service.archive(db, staff, item_id)))


@admin.post(
    "/{item_id}/attachment",
    response_model=ApiResponse[AdminContent],
    responses={**_ERR, 413: {"model": ErrorResponse}, 415: {"model": ErrorResponse}},
    summary="Attach a downloadable document with a version label (draft only)",
)
def attachment(
    item_id: uuid.UUID,
    request: Request,
    staff: ContentAdminDep,
    db: DbSession,
    settings: SettingsDep,
    file: Annotated[UploadFile, File()],
    version_label: Annotated[str | None, Form(max_length=40)] = None,
) -> ApiResponse[AdminContent]:
    return ok(
        _adm(
            service.set_attachment(
                db, request.app.state.storage, settings, staff, item_id, file, version_label
            )
        )
    )


# ------------------------------------------------------- claims register
claims = APIRouter(prefix="/admin/content-claims", tags=["admin-content-claims"])


class ClaimIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_text: Long
    category: ClaimCategory
    evidence_ref: Annotated[str, Field(max_length=300)] | None = None


class ClaimUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_text: Long | None = None
    category: ClaimCategory | None = None
    evidence_ref: Annotated[str, Field(max_length=300)] | None = None
    evidence_status: ClaimStatus | None = Field(
        default=None, description="Super administrator only"
    )
    publication_permission: bool | None = Field(
        default=None, description="Super administrator only"
    )


class ClaimOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    claim_text: str
    category: ClaimCategory
    owner_id: uuid.UUID
    evidence_status: ClaimStatus
    evidence_ref: str | None
    publication_permission: bool
    last_reviewed_at: datetime | None


@claims.post(
    "",
    status_code=201,
    response_model=ApiResponse[ClaimOut],
    responses=_ERR,
    summary="Register a public claim (starts as pending_verification)",
)
def create_claim(payload: ClaimIn, staff: ContentAdminDep, db: DbSession) -> ApiResponse[ClaimOut]:
    return ok(ClaimOut.model_validate(service.create_claim(db, staff, payload.model_dump())))


@claims.get("", response_model=ApiResponse[list[ClaimOut]], responses=_ERR)
def list_claims(
    staff: ContentAdminDep,
    db: DbSession,
    page: PageDep,
    status: Annotated[ClaimStatus | None, Query()] = None,
    category: Annotated[ClaimCategory | None, Query()] = None,
) -> ApiResponse[list[ClaimOut]]:
    rows, total = service.list_claims(db, page.page_size, page.offset, status, category)
    return ok([ClaimOut.model_validate(c) for c in rows], meta=page_meta(page, total))


@claims.patch(
    "/{claim_id}",
    response_model=ApiResponse[ClaimOut],
    responses=_ERR,
    summary="Edit a claim (verification: super administrator). Un-clearing pulls content offline",
)
def update_claim(
    claim_id: uuid.UUID, payload: ClaimUpdate, staff: ContentAdminDep, db: DbSession
) -> ApiResponse[ClaimOut]:
    return ok(
        ClaimOut.model_validate(
            service.update_claim(
                db, staff, claim_id, payload.model_dump(exclude_unset=True, exclude_none=True)
            )
        )
    )
