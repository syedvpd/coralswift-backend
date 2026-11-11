"""Partner email preferences. Mandatory categories cannot be switched off (account security and
invitations) and application decisions/requests (D42). Only acknowledgements are optional."""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.notifications.constants import NotificationType
from app.modules.notifications.models import PartnerNotificationPreference

MANDATORY = frozenset({NotificationType.ACCOUNT.value, NotificationType.APPLICATION.value})
OPTIONAL = frozenset({NotificationType.ACKNOWLEDGEMENT.value})


def is_muted(db: Session, recipient: str, kind: NotificationType) -> bool:
    """True when the recipient is a partner user who switched this optional category off."""
    if kind.value not in OPTIONAL:
        return False
    row = db.execute(
        select(PartnerNotificationPreference.enabled)
        .join(User, User.id == PartnerNotificationPreference.user_id)
        .where(
            User.email == recipient.lower(),
            PartnerNotificationPreference.category == kind.value,
        )
    ).first()
    return row is not None and row[0] is False


def load(db: Session, user_id: uuid.UUID) -> dict[str, bool]:
    stored = dict(
        db.execute(
            select(
                PartnerNotificationPreference.category, PartnerNotificationPreference.enabled
            ).where(PartnerNotificationPreference.user_id == user_id)
        ).all()
    )
    return {c: stored.get(c, True) for c in sorted(MANDATORY | OPTIONAL)} | {
        c: True for c in MANDATORY
    }


def save(db: Session, user_id: uuid.UUID, changes: dict[str, bool], now: datetime) -> None:
    for category, enabled in changes.items():
        row = db.get(PartnerNotificationPreference, (user_id, category))
        if row is None:
            db.add(
                PartnerNotificationPreference(
                    user_id=user_id, category=category, enabled=enabled, updated_at=now
                )
            )
        else:
            row.enabled, row.updated_at = enabled, now
