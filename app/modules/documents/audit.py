"""Audit trail for refused document downloads (successful ones are audited where they happen)."""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.modules.enquiries.activity import log_activity
from app.modules.enquiries.constants import ActorType


@contextmanager
def audit_denied_download(
    db: Session,
    document_id: uuid.UUID,
    *,
    actor_type: ActorType,
    actor_user_id: uuid.UUID,
    organization_id: uuid.UUID | None = None,
) -> Iterator[None]:
    """A 403/404/409 while serving a document is recorded as `document.download_denied`
    (outcome failure) before the error reaches the caller. No file or owner data is logged."""
    try:
        yield
    except AppError as exc:
        if exc.status_code in (403, 404, 409):
            db.rollback()
            log_activity(
                db,
                "document",
                document_id,
                "document.download_denied",
                {"code": exc.code, "status": exc.status_code},
                actor_type,
                actor_user_id=actor_user_id,
                organization_id=organization_id,
            )
            db.commit()
        raise
