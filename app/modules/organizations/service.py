import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.utilities import utcnow
from app.core.exceptions import AppError
from app.modules.auth.dependencies import PartnerContext
from app.modules.auth.models import User
from app.modules.enquiries.activity import log_activity
from app.modules.enquiries.constants import ActorType
from app.modules.organizations.constants import MIN_CLIENT_REFERENCES, REQUIRED_PROFILE_FIELDS
from app.modules.organizations.models import PartnerOrganization, PartnerProfileRevision
from app.modules.organizations.schemas import CompletionOut, ProfileUpdate


def create_organization(
    db: Session,
    *,
    creator: User,
    legal_name: str,
    source_enquiry_id: uuid.UUID | None = None,
) -> PartnerOrganization:
    """Always creates a NEW organization; never merges with an existing one by name or email."""
    org = PartnerOrganization(legal_name=legal_name, source_enquiry_id=source_enquiry_id)
    db.add(org)
    db.flush()
    log_activity(
        db,
        "organization",
        org.id,
        "organization.created",
        {"source_enquiry": source_enquiry_id is not None},
        ActorType.REVIEWER,
        actor_user_id=creator.id,
        organization_id=org.id,
    )
    return org


def get_organization(
    db: Session, organization_id: uuid.UUID, *, lock: bool = False
) -> PartnerOrganization:
    stmt = select(PartnerOrganization).where(PartnerOrganization.id == organization_id)
    if lock:
        stmt = stmt.with_for_update()
    return db.execute(stmt).scalar_one()


def get_organization_or_none(db: Session, organization_id: uuid.UUID) -> PartnerOrganization | None:
    return db.get(PartnerOrganization, organization_id)


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if hasattr(value, "value"):  # enum
        return value.value
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump(mode="json"))
    return value


def _is_empty(value: Any) -> bool:
    return value is None or value in ("", [], {})


def update_profile(db: Session, ctx: PartnerContext, data: ProfileUpdate) -> PartnerOrganization:
    """D19: a partner may fill a field that is still empty; changing or clearing a value that is
    already set goes through a change request that staff approve."""
    org = get_organization(db, ctx.organization_id)
    if data.expected_version is not None and data.expected_version != org.profile_version:
        raise AppError(
            "The profile was changed by someone else; reload and retry",
            status_code=409,
            code="PROFILE_VERSION_CONFLICT",
        )
    locked: list[str] = []
    for field, new in data.model_dump(exclude_unset=True, exclude={"expected_version"}).items():
        if field == "legal_name" and new is None:
            continue  # rejected below as not clearable (422)
        current = _jsonable(getattr(org, field))
        if not _is_empty(current) and _jsonable(new) != current:
            locked.append(field)
    if locked:
        raise AppError(
            "These fields already have a value; submit a change request: "
            + ", ".join(sorted(locked)),
            status_code=409,
            code="CHANGE_REQUEST_REQUIRED",
        )
    return apply_profile_update(db, ctx.organization_id, ctx.user.id, data, ActorType.PARTNER)


def apply_profile_update(
    db: Session,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    data: ProfileUpdate,
    actor: ActorType,
    *,
    commit: bool = True,
) -> PartnerOrganization:
    # Row lock serialises concurrent edits of the same organization.
    org = get_organization(db, organization_id, lock=True)
    if data.expected_version is not None and data.expected_version != org.profile_version:
        raise AppError(
            "The profile was changed by someone else; reload and retry",
            status_code=409,
            code="PROFILE_VERSION_CONFLICT",
        )
    changes: dict[str, Any] = {}
    for field, new in data.model_dump(exclude_unset=True, exclude={"expected_version"}).items():
        if new is None:
            if field == "legal_name":
                raise AppError(
                    "Legal name cannot be cleared", status_code=422, code="FIELD_NOT_CLEARABLE"
                )
            old_json = _jsonable(getattr(org, field))
            if old_json is None:
                continue
            changes[field] = {"old": old_json, "new": None}
            setattr(org, field, None)
            continue
        new_json = _jsonable(new)
        old_json = _jsonable(getattr(org, field))
        if new_json == old_json:
            continue
        changes[field] = {"old": old_json, "new": new_json}
        setattr(org, field, [_jsonable(v) for v in new] if isinstance(new, list) else new)
    if not changes:
        if commit:
            db.rollback()  # release the row lock
        return org
    org.profile_version += 1
    db.add(
        PartnerProfileRevision(
            organization_id=org.id,
            version=org.profile_version,
            changed_by=user_id,
            changes=changes,
            created_at=utcnow(),
        )
    )
    log_activity(
        db,
        "organization",
        org.id,
        "organization.profile_updated",
        {"fields": sorted(changes), "version": org.profile_version},  # field names only
        actor,
        actor_user_id=user_id,
        organization_id=org.id,
    )
    if commit:
        db.commit()
    return org


def completion(org: PartnerOrganization) -> CompletionOut:
    missing: list[str] = []
    for name in REQUIRED_PROFILE_FIELDS:
        value = getattr(org, name)
        too_few_refs = name == "client_references" and len(value or []) < MIN_CLIENT_REFERENCES
        if value is None or value == "" or value == [] or too_few_refs:
            missing.append(name)
    total = len(REQUIRED_PROFILE_FIELDS)
    return CompletionOut(
        percent=round(100 * (total - len(missing)) / total),
        missing_fields=missing,
        complete=not missing,
    )


def list_revisions(db: Session, organization_id: uuid.UUID) -> list[PartnerProfileRevision]:
    return list(
        db.execute(
            select(PartnerProfileRevision)
            .where(PartnerProfileRevision.organization_id == organization_id)
            .order_by(PartnerProfileRevision.version.desc())
        ).scalars()
    )
