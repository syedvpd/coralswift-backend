import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import request_id_var
from app.modules.enquiries.constants import ActorType
from app.modules.enquiries.models import Activity


def log_activity(
    db: Session,
    record_type: str,
    record_id: uuid.UUID,
    action: str,
    meta: dict[str, Any] | None = None,
    actor: ActorType = ActorType.PUBLIC,
    *,
    actor_user_id: uuid.UUID | None = None,
    organization_id: uuid.UUID | None = None,
) -> None:
    """Append an audit row (the table is immutable at DB level).

    `meta` must hold no PII, credentials, tokens or free-text notes: field names and codes only.
    """
    db.add(
        Activity(
            record_type=record_type,
            record_id=record_id,
            action=action,
            actor_type=actor,
            meta=meta or {},
            actor_user_id=actor_user_id,
            organization_id=organization_id,
            request_id=request_id_var.get(),
        )
    )
