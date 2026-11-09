"""DB-backed idempotency for public submissions.

Flow: claim (own committed txn, unique constraint decides the winner) -> do the work and store the
response in the SAME txn as the work -> commit. A failed attempt releases its claim so the client
can retry. Rows expire after `idempotency_ttl_hours`; `purge_expired` removes them.
"""

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import (
    DateTime,
    Index,
    SmallInteger,
    String,
    UniqueConstraint,
    delete,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.common.utilities import utcnow
from app.core.exceptions import AppError
from app.database.base import Base, UUIDPrimaryKeyMixin

KEY_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{8,128}$")
STALE_CLAIM = timedelta(seconds=60)  # an in_progress claim older than this is treated as crashed


class IdempotencyKey(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "idempotency_keys"

    scope: Mapped[str] = mapped_column(String(100))  # endpoint
    client_hash: Mapped[str] = mapped_column(String(64))  # sha256(client ip)
    key: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    completed: Mapped[bool] = mapped_column(default=False)
    response_status: Mapped[int | None] = mapped_column(SmallInteger)
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("scope", "client_hash", "key", name="uq_idempotency_scope_client_key"),
        Index("ix_idempotency_expires_at", "expires_at"),
    )


@dataclass(frozen=True)
class IdemContext:
    id: uuid.UUID
    scope: str
    client_hash: str
    key: str
    request_hash: str


@dataclass(frozen=True)
class Replay:
    status_code: int
    body: dict[str, Any]


def validate_key(key: str) -> str:
    if not KEY_PATTERN.match(key):
        raise AppError(
            "Idempotency-Key must be 8-128 chars of letters, digits, '_', '-', '.', ':'",
            status_code=422,
            code="INVALID_IDEMPOTENCY_KEY",
        )
    return key


def hash_payload(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def hash_client(ip: str) -> str:
    return hashlib.sha256(ip.encode()).hexdigest()


def claim(
    db: Session,
    *,
    scope: str,
    client_ip: str,
    key: str,
    payload: dict[str, Any],
    ttl_hours: int,
) -> IdemContext | Replay:
    """Commit a claim for this key, or return the stored response of an earlier completed call."""
    ctx = IdemContext(uuid.uuid4(), scope, hash_client(client_ip), key, hash_payload(payload))
    for _ in range(3):
        now = utcnow()
        inserted = db.execute(
            pg_insert(IdempotencyKey)
            .values(
                id=ctx.id,
                scope=scope,
                client_hash=ctx.client_hash,
                key=key,
                request_hash=ctx.request_hash,
                created_at=now,
                expires_at=now + timedelta(hours=ttl_hours),
            )
            .on_conflict_do_nothing(constraint="uq_idempotency_scope_client_key")
            .returning(IdempotencyKey.id)
        ).first()
        if inserted:
            db.commit()
            return ctx
        db.rollback()
        existing = db.execute(
            select(IdempotencyKey).where(
                IdempotencyKey.scope == scope,
                IdempotencyKey.client_hash == ctx.client_hash,
                IdempotencyKey.key == key,
            )
        ).scalar_one_or_none()
        if existing is None:
            continue  # released between our insert and select: try again
        expired = existing.expires_at <= now
        crashed = not existing.completed and now - existing.created_at > STALE_CLAIM
        if expired or crashed:
            db.execute(delete(IdempotencyKey).where(IdempotencyKey.id == existing.id))
            db.commit()
            continue
        if existing.request_hash != ctx.request_hash:
            raise AppError(
                "This Idempotency-Key was already used with a different request",
                status_code=422,
                code="IDEMPOTENCY_KEY_REUSED",
            )
        if existing.completed and existing.response_body is not None:
            return Replay(existing.response_status or 200, existing.response_body)
        raise AppError(
            "An identical request is still being processed",
            status_code=409,
            code="REQUEST_IN_PROGRESS",
            headers={"Retry-After": "2"},
        )
    raise AppError("Could not acquire idempotency key", status_code=409, code="REQUEST_IN_PROGRESS")


def complete(db: Session, ctx: IdemContext, status_code: int, body: dict[str, Any]) -> None:
    """Record the response inside the caller's transaction (commit happens with the work)."""
    db.execute(
        update(IdempotencyKey)
        .where(IdempotencyKey.id == ctx.id)
        .values(completed=True, response_status=status_code, response_body=body)
    )


def release(db: Session, ctx: IdemContext) -> None:
    """Drop the claim after a failed attempt so the client may retry with the same key."""
    db.rollback()
    db.execute(delete(IdempotencyKey).where(IdempotencyKey.id == ctx.id, ~IdempotencyKey.completed))
    db.commit()


def purge_expired(db: Session) -> int:
    result = db.execute(delete(IdempotencyKey).where(IdempotencyKey.expires_at <= utcnow()))
    db.commit()
    return int(getattr(result, "rowcount", 0))
