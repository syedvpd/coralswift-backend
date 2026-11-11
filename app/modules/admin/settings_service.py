"""System settings (PRD s.14, s.28). Only registered keys can be stored; every value is validated.
With nothing stored no SLA, routing, retention or reminders are active: the PRD leaves those
numbers and owners to the business (s.25, s.28), so none are invented here."""

import re
import uuid
from collections.abc import Callable

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.common.utilities import utcnow
from app.core.exceptions import AppError
from app.modules.admin.models import SystemSetting
from app.modules.auth.constants import StaffRole, UserStatus
from app.modules.auth.models import User
from app.modules.enquiries.constants import EnquiryType
from app.modules.partners.constants import EngagementPathway

QUEUES = [t.value for t in EnquiryType]
CONTACT_ITEMS = ["domain", "email", "address", "phone", "representative"]


def _int(lo: int, hi: int) -> Callable[[str], str]:
    def check(v: str) -> str:
        n = int(v)
        if not lo <= n <= hi:
            raise ValueError(f"{lo}..{hi}")
        return str(n)

    return check


def _bool(v: str) -> str:
    if v.lower() not in ("true", "false"):
        raise ValueError("true or false")
    return v.lower()


def _email(v: str) -> str:
    try:
        return str(validate_email(v, check_deliverability=False).normalized).lower()
    except EmailNotValidError as exc:
        raise ValueError("invalid email") from exc


def _uuid(v: str) -> str:
    return str(uuid.UUID(v))


def _text(v: str) -> str:
    if not v or len(v) > 300 or "\x00" in v:
        raise ValueError("1..300 characters")
    return v


def _categories(v: str) -> str:
    """Comma list of document categories (D6: required documents per pathway, owner-defined)."""
    from app.modules.partner_documents.constants import PartnerDocCategory

    items = [i.strip() for i in v.split(",") if i.strip()]
    if not items or len(set(items)) != len(items):
        raise ValueError("a comma-separated list without duplicates")
    valid = {c.value for c in PartnerDocCategory}
    if any(i not in valid for i in items):
        raise ValueError("unknown document category")
    return ",".join(items)


def _onboarding_template(v: str) -> str:
    """JSON list of {name, required_action?, due_in_days?, document_category?} (D10)."""
    import json

    from app.modules.partner_documents.constants import PartnerDocCategory

    data = json.loads(v)
    if not isinstance(data, list) or len(data) > 50:
        raise ValueError("a JSON list of at most 50 tasks")
    valid = {c.value for c in PartnerDocCategory}
    for t in data:
        if (
            not isinstance(t, dict)
            or not isinstance(t.get("name"), str)
            or not 1 <= len(t["name"]) <= 200
            or set(t) - {"name", "required_action", "due_in_days", "document_category"}
            or (t.get("due_in_days") is not None and not isinstance(t["due_in_days"], int))
            or (t.get("document_category") is not None and t["document_category"] not in valid)
        ):
            raise ValueError("invalid task entry")
    return json.dumps(data, separators=(",", ":"))


def _domain(v: str) -> str:
    if not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}", v.lower()):
        raise ValueError("invalid domain")
    return v.lower()


def _phone(v: str) -> str:
    cleaned = re.sub(r"[\s().-]", "", v)
    if not re.fullmatch(r"\+[1-9][0-9]{6,14}", cleaned):
        raise ValueError("international format, e.g. +14155550123")
    return cleaned


REGISTRY: dict[str, Callable[[str], str]] = {
    **{f"sla.{q}": _int(1, 24 * 90) for q in QUEUES},  # first-response target, hours
    **{f"sla_escalation.{q}": _int(1, 24 * 90) for q in QUEUES},  # escalation target, hours
    **{f"route.owner.{q}": _uuid for q in QUEUES},  # default lead owner (staff user id)
    **{f"route.backup.{q}": _uuid for q in QUEUES},  # out-of-office cover for the owner
    **{f"escalation.email.{q}": _email for q in QUEUES},  # told when a target is missed
    "ack_promise_enabled": _bool,  # s.28: acknowledgement wording may promise the SLA only if true
    "retention.partner_document_days": _int(1, 3650),
    **{f"required_documents.{p.value}": _categories for p in EngagementPathway},
    "onboarding.template": _onboarding_template,
    # Privacy targets: provisional 30 days / 72 h pending legal review; unset = no due date
    "privacy.completion_days": _int(1, 365),
    "privacy.verification_hours": _int(1, 720),
    "expiry_reminder_days": _int(1, 365),
    "contact.domain": _domain,
    "contact.email": _email,
    "contact.address": _text,
    "contact.phone": _phone,
    "contact.representative": _text,
    **{f"contact.{i}.omitted": _bool for i in CONTACT_ITEMS},  # "intentionally omitted" (s.28)
}


def get(db: Session, key: str) -> str | None:
    row = db.get(SystemSetting, key)
    return row.value if row else None


def get_int(db: Session, key: str) -> int | None:
    value = get(db, key)
    return int(value) if value and value.isdigit() else None


def is_true(db: Session, key: str) -> bool:
    return get(db, key) == "true"


def list_all(db: Session) -> dict[str, str]:
    return {r.key: r.value for r in db.execute(select(SystemSetting)).scalars()}


def valid_owner(db: Session, user_id: uuid.UUID, queue: str) -> User | None:
    """Active staff user allowed to own this queue (strategic: super administrators only)."""
    owner = db.get(User, user_id)
    allowed = {StaffRole.BUSINESS_DEVELOPMENT_MANAGER, StaffRole.SUPER_ADMINISTRATOR}
    if queue == EnquiryType.STRATEGIC.value:
        allowed = {StaffRole.SUPER_ADMINISTRATOR}
    if owner and owner.status is UserStatus.ACTIVE and owner.staff_role in allowed:
        return owner
    return None


def put(db: Session, key: str, value: str, user_id: uuid.UUID) -> str:
    check = REGISTRY.get(key)
    if check is None:
        raise AppError("Unknown setting", status_code=422, code="UNKNOWN_SETTING")
    try:
        cleaned = check(value.strip())
    except ValueError as exc:
        raise AppError(
            f"Invalid value for {key}: {exc}", status_code=422, code="INVALID_SETTING"
        ) from None
    is_owner_key = key.startswith(("route.owner.", "route.backup."))
    if is_owner_key and valid_owner(db, uuid.UUID(cleaned), key.rsplit(".", 1)[1]) is None:
        raise AppError("Not a valid owner for this queue", status_code=422, code="INVALID_OWNER")
    row = db.get(SystemSetting, key)
    if row is None:
        db.add(SystemSetting(key=key, value=cleaned, updated_by=user_id, updated_at=utcnow()))
    else:
        row.value, row.updated_by, row.updated_at = cleaned, user_id, utcnow()
    return cleaned


def remove(db: Session, key: str) -> None:
    if key not in REGISTRY:
        raise AppError("Unknown setting", status_code=422, code="UNKNOWN_SETTING")
    db.execute(delete(SystemSetting).where(SystemSetting.key == key))
