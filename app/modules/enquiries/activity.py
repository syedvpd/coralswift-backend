import re
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import client_ip_var, request_id_var, user_agent_var
from app.modules.enquiries.constants import ActorType
from app.modules.enquiries.models import Activity

_FAILED = re.compile(r"failed|blocked|denied|reuse_detected")


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
    changes: dict[str, dict[str, Any]] | None = None,
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
            meta=({**(meta or {}), "changes": changes} if changes else (meta or {})),
            actor_user_id=actor_user_id,
            organization_id=organization_id,
            request_id=request_id_var.get(),
            ip_address=client_ip_var.get(),
            user_agent=user_agent_var.get(),
            outcome="failure" if _FAILED.search(action) else "success",
        )
    )
