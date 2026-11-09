"""Queue routing and SLA targets for new enquiries (PRD s.15B, s.28). Driven only by stored system
settings; with none configured nothing changes (no owner, no deadline)."""

import uuid
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.modules.admin import settings_service as cfg
from app.modules.enquiries.models import Enquiry


def apply_routing(db: Session, enquiry: Enquiry, now: datetime) -> int | None:
    """Set default owner (with out-of-office backup) and first-response deadline.
    Returns the SLA hours when configured.

    shortcut: the deadline is plain elapsed hours; business hours/holidays are undefined in the PRD.
    """
    queue = enquiry.enquiry_type.value
    hours = cfg.get_int(db, f"sla.{queue}")
    if hours:
        enquiry.response_due_at = now + timedelta(hours=hours)
    for key in (f"route.owner.{queue}", f"route.backup.{queue}"):
        user_id = cfg.get(db, key)
        owner = cfg.valid_owner(db, uuid.UUID(user_id), queue) if user_id else None
        if owner:
            enquiry.assigned_user_id = owner.id
            break
    return hours
