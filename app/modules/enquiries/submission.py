"""Shared submit pipeline: idempotency claim -> create (one transaction) -> commit -> notify."""

from collections.abc import Callable
from typing import Annotated

from fastapi import BackgroundTasks, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.common import idempotency
from app.common.responses import ok
from app.core.config import Settings
from app.core.protection import client_ip
from app.modules.enquiries.service import Created
from app.modules.notifications.service import dispatch_notifications

IdempotencyKeyHeader = Annotated[
    str | None,
    Header(
        alias="Idempotency-Key",
        description="Optional, 8-128 chars; same key and body returns the original result.",
    ),
]
SUCCESS_MESSAGE = "Submission received"


def execute_submission(
    *,
    request: Request,
    db: Session,
    settings: Settings,
    background: BackgroundTasks,
    payload: BaseModel,
    idem_key: str | None,
    create: Callable[[], Created],
) -> JSONResponse:
    ctx: idempotency.IdemContext | None = None
    if idem_key is not None:
        claimed = idempotency.claim(
            db,
            scope=f"{request.method} {request.url.path}",
            client_ip=client_ip(request),
            key=idempotency.validate_key(idem_key),
            payload=payload.model_dump(mode="json"),
            ttl_hours=settings.idempotency_ttl_hours,
        )
        if isinstance(claimed, idempotency.Replay):
            return JSONResponse(
                claimed.body, status_code=claimed.status_code, headers={"Idempotent-Replay": "true"}
            )
        ctx = claimed
    try:
        created = create()
        body = ok(created.out, SUCCESS_MESSAGE).model_dump(mode="json")
        if ctx:
            idempotency.complete(db, ctx, 201, body)
        db.commit()
    except Exception:
        if ctx:
            idempotency.release(db, ctx)
        else:
            db.rollback()
        raise
    # After commit only: a rolled-back submission never produces an email.
    background.add_task(
        dispatch_notifications,
        request.app.state.sessionmaker,
        request.app.state.email_sender,
        settings,
        created.enquiry.id,
    )
    return JSONResponse(body, status_code=201)
