"""CMS media library: image upload by content staff, explicit publish before public serving."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select

from app.common.pagination import PageDep, page_meta
from app.common.responses import ApiResponse, ErrorResponse, ok
from app.common.utilities import utcnow
from app.core.config import Settings, get_settings
from app.core.exceptions import AppError, NotFoundError
from app.core.protection import rate_limit
from app.database.dependencies import DbSession
from app.integrations.storage import StorageError
from app.modules.admin import lookups
from app.modules.auth.constants import StaffRole
from app.modules.auth.dependencies import StaffContext, require_staff
from app.modules.documents.files import validate_upload
from app.modules.enquiries.activity import log_activity
from app.modules.enquiries.constants import ActorType
from app.modules.media.models import MediaAsset

SettingsDep = Annotated[Settings, Depends(get_settings)]
ContentAdminDep = Annotated[
    StaffContext,
    Depends(require_staff(StaffRole.CONTENT_ADMINISTRATOR, StaffRole.SUPER_ADMINISTRATOR)),
]
_ERR: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    413: {"model": ErrorResponse},
    415: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}
admin = APIRouter(prefix="/admin/media", tags=["admin-media"])
public = APIRouter(prefix="/media", tags=["media"])
IMAGE_KINDS = {"png", "jpg"}


class MediaOut(BaseModel):
    id: uuid.UUID
    original_filename: str
    content_type: str
    file_size: int
    alt_text: str | None
    is_public: bool
    public_url_path: str | None
    uploaded_by_name: str | None
    created_at: datetime
    archived_at: datetime | None


def _out(m: MediaAsset, names: dict[uuid.UUID, str]) -> MediaOut:
    return MediaOut(
        id=m.id,
        original_filename=m.original_filename,
        content_type=m.content_type,
        file_size=m.file_size,
        alt_text=m.alt_text,
        is_public=m.is_public,
        public_url_path=f"/media/{m.id}/file" if m.is_public and not m.archived_at else None,
        uploaded_by_name=names.get(m.uploaded_by),
        created_at=m.created_at,
        archived_at=m.archived_at,
    )


def _get(db: DbSession, asset_id: uuid.UUID, lock: bool = False) -> MediaAsset:
    stmt = select(MediaAsset).where(MediaAsset.id == asset_id)
    m = db.execute(stmt.with_for_update() if lock else stmt).scalar_one_or_none()
    if m is None:
        raise NotFoundError("Media not found")
    return m


def _audit(db: DbSession, staff: StaffContext, m: MediaAsset, action: str) -> None:
    log_activity(db, "media", m.id, action, None, ActorType.STAFF, actor_user_id=staff.user.id)


@admin.post(
    "",
    status_code=201,
    dependencies=[Depends(rate_limit("upload", 2))],
    response_model=ApiResponse[MediaOut],
    responses=_ERR,
    summary="Upload an image (png or jpg, size limit as documents); private until published",
)
def upload(
    request: Request,
    staff: ContentAdminDep,
    db: DbSession,
    settings: SettingsDep,
    file: Annotated[UploadFile, File()],
    alt_text: Annotated[str | None, Form(max_length=200)] = None,
) -> ApiResponse[MediaOut]:
    data = file.file.read(settings.max_upload_bytes + 1)
    checked = validate_upload(
        data=data,
        filename=file.filename,
        declared_type=file.content_type,
        max_bytes=settings.max_upload_bytes,
    )
    if checked.kind.extension not in IMAGE_KINDS:
        raise AppError("Only png and jpg images are accepted", status_code=415, code="NOT_AN_IMAGE")
    now = utcnow()
    key = f"cms/media/{now:%Y/%m}/{uuid.uuid4().hex}.{checked.kind.extension}"
    try:
        request.app.state.storage.put(key, data, checked.kind.content_type)
    except StorageError:
        raise AppError(
            "File storage is unavailable", status_code=503, code="STORAGE_UNAVAILABLE"
        ) from None
    m = MediaAsset(
        storage_key=key,
        original_filename=checked.display_name,
        content_type=checked.kind.content_type,
        file_size=checked.size,
        checksum=checked.sha256,
        alt_text=alt_text,
        uploaded_by=staff.user.id,
        created_at=now,
    )
    db.add(m)
    db.flush()
    _audit(db, staff, m, "media.uploaded")
    db.commit()
    return ok(_out(m, {staff.user.id: staff.user.full_name}), "Uploaded")


@admin.get("", response_model=ApiResponse[list[MediaOut]], responses=_ERR)
def list_media(
    staff: ContentAdminDep,
    db: DbSession,
    page: PageDep,
    published: Annotated[bool | None, Query()] = None,
    archived: Annotated[bool, Query()] = False,
    q: Annotated[str | None, Query(max_length=100, description="filename or alt text")] = None,
) -> ApiResponse[list[MediaOut]]:
    stmt = select(MediaAsset).where(
        MediaAsset.archived_at.is_not(None) if archived else MediaAsset.archived_at.is_(None)
    )
    if published is not None:
        stmt = stmt.where(MediaAsset.is_public.is_(published))
    if q:
        like = "%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        stmt = stmt.where(
            MediaAsset.original_filename.ilike(like) | MediaAsset.alt_text.ilike(like)
        )
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = list(
        db.execute(
            stmt.order_by(MediaAsset.created_at.desc(), MediaAsset.id)
            .limit(page.page_size)
            .offset(page.offset)
        ).scalars()
    )
    names = lookups.user_names(db, (r.uploaded_by for r in rows))
    return ok([_out(r, names) for r in rows], meta=page_meta(page, total))


@admin.get(
    "/{asset_id}/file",
    responses={**_ERR, 200: {"content": {"image/png": {}, "image/jpeg": {}}}},
    summary="Preview the stored image (authenticated; works before publishing)",
)
def preview(
    asset_id: uuid.UUID, request: Request, staff: ContentAdminDep, db: DbSession
) -> Response:
    m = _get(db, asset_id)
    return Response(
        content=request.app.state.storage.get(m.storage_key),
        media_type=m.content_type,
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


def _set(db: DbSession, staff: StaffContext, asset_id: uuid.UUID, action: str) -> MediaAsset:
    m = _get(db, asset_id, lock=True)
    if action == "publish":
        if m.archived_at:
            raise AppError("Archived media cannot be published", status_code=409, code="ARCHIVED")
        m.is_public = True
    elif action == "unpublish":
        m.is_public = False
    else:
        m.archived_at, m.is_public = utcnow(), False
    _audit(db, staff, m, f"media.{action}ed" if action != "archive" else "media.archived")
    db.commit()
    return m


@admin.post("/{asset_id}/publish", response_model=ApiResponse[MediaOut], responses=_ERR)
def publish(asset_id: uuid.UUID, staff: ContentAdminDep, db: DbSession) -> ApiResponse[MediaOut]:
    return ok(_out(_set(db, staff, asset_id, "publish"), {}), "Published")


@admin.post("/{asset_id}/unpublish", response_model=ApiResponse[MediaOut], responses=_ERR)
def unpublish(asset_id: uuid.UUID, staff: ContentAdminDep, db: DbSession) -> ApiResponse[MediaOut]:
    return ok(_out(_set(db, staff, asset_id, "unpublish"), {}), "Unpublished")


@admin.post(
    "/{asset_id}/archive",
    response_model=ApiResponse[MediaOut],
    responses=_ERR,
    summary="Hide from the library and public serving (the file is kept)",
)
def archive(asset_id: uuid.UUID, staff: ContentAdminDep, db: DbSession) -> ApiResponse[MediaOut]:
    return ok(_out(_set(db, staff, asset_id, "archive"), {}), "Archived")


@public.get(
    "/{asset_id}/file",
    responses={**_ERR, 200: {"content": {"image/png": {}, "image/jpeg": {}}}},
    dependencies=[Depends(rate_limit("content-download", 3))],
    summary="A published image. Unpublished or archived media answers 404",
)
def public_file(asset_id: uuid.UUID, request: Request, db: DbSession) -> Response:
    m = db.execute(
        select(MediaAsset).where(
            MediaAsset.id == asset_id,
            MediaAsset.is_public.is_(True),
            MediaAsset.archived_at.is_(None),
        )
    ).scalar_one_or_none()
    if m is None:
        raise NotFoundError("Media not found")
    return Response(
        content=request.app.state.storage.get(m.storage_key),
        media_type=m.content_type,
        headers={"Cache-Control": "public, max-age=300", "X-Content-Type-Options": "nosniff"},
    )
