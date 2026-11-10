"""Small batch lookups shared by admin responses: actor names and strategic classification."""

import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.enquiries.constants import EnquiryType
from app.modules.enquiries.models import Enquiry


def user_names(db: Session, ids: Iterable[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    """id -> full name for the given users (one query). Unknown or null ids are skipped."""
    wanted = {i for i in ids if i}
    if not wanted:
        return {}
    rows = db.execute(select(User.id, User.full_name).where(User.id.in_(wanted))).all()
    return {i: name for i, name in rows}


def strategic_enquiry_ids(db: Session, ids: Iterable[uuid.UUID | None]) -> set[uuid.UUID]:
    """Which of the given enquiry ids are strategic/M&A (one query)."""
    wanted = {i for i in ids if i}
    if not wanted:
        return set()
    return set(
        db.execute(
            select(Enquiry.id).where(
                Enquiry.id.in_(wanted), Enquiry.enquiry_type == EnquiryType.STRATEGIC
            )
        ).scalars()
    )
