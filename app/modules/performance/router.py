"""Partner performance foundation: staff record and publish, partners read published rows only."""

import csv
import enum
import io
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.common.pagination import PageDep, page_meta
from app.common.responses import ApiResponse, ErrorResponse, ok
from app.common.utilities import utcnow
from app.common.validation import Long
from app.core.exceptions import AppError, NotFoundError
from app.database.dependencies import DbSession
from app.modules.admin import settings_service as cfg
from app.modules.applications.models import PortalApplication
from app.modules.auth.dependencies import PartnerDep, ReviewerDep, StaffContext
from app.modules.collaboration import service as collab
from app.modules.documents.constants import attachable_statuses
from app.modules.enquiries.activity import log_activity
from app.modules.enquiries.constants import ActorType
from app.modules.partner_documents.constants import DocStatus, ReviewStatus
from app.modules.partner_documents.models import PartnerDocument, PartnerDocumentVersion
from app.modules.performance.models import PerformanceEntry, PerformanceFeedback

_ERR: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}
partner = APIRouter(prefix="/partner/performance", tags=["partner-performance"])
staff = APIRouter(prefix="/reviewer", tags=["reviewer-performance"])
Period = Annotated[
    str, Field(pattern=r"^[0-9]{4}(-(Q[1-4]|[0-1][0-9]))?$", description="2026, 2026-Q3 or 2026-09")
]


class IndicatorKey(enum.StrEnum):
    APPLICATION_TURNAROUND_DAYS = "application_turnaround_days"
    DOCUMENT_COMPLETENESS_PERCENTAGE = "document_completeness_percentage"


# Calculation definitions shown to partners (D39). Nothing else is ever computed or published.
DEFINITIONS = {
    IndicatorKey.APPLICATION_TURNAROUND_DAYS: (
        "Average days between submission and the recorded decision, over this organisation's "
        "applications whose decision was recorded in the period. Undecided applications are "
        "excluded."
    ),
    IndicatorKey.DOCUMENT_COMPLETENESS_PERCENTAGE: (
        "Accepted, current and unexpired required document categories divided by all required "
        "document categories for the organisation's pathway, times 100. Unavailable until the "
        "required categories for the pathway are defined."
    ),
}
LABELS = {
    IndicatorKey.APPLICATION_TURNAROUND_DAYS: "Application turnaround (days)",
    IndicatorKey.DOCUMENT_COMPLETENESS_PERCENTAGE: "Document completeness (%)",
}
UNITS = {
    IndicatorKey.APPLICATION_TURNAROUND_DAYS: "days",
    IndicatorKey.DOCUMENT_COMPLETENESS_PERCENTAGE: "percent",
}
Key = IndicatorKey


class IndicatorOut(BaseModel):
    id: uuid.UUID
    period: str
    indicator_key: str
    label: str
    value: Decimal
    unit: str | None
    definition: str
    published_at: datetime | None


class StaffIndicatorOut(IndicatorOut):
    is_published: bool
    organization_id: uuid.UUID


class ScorecardOut(BaseModel):
    period: str
    indicators: list[IndicatorOut]


class FeedbackOut(BaseModel):
    id: uuid.UUID
    period: str
    text: str
    published_at: datetime | None


class StaffFeedbackOut(FeedbackOut):
    is_published: bool
    organization_id: uuid.UUID


class EntryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period: Period
    indicator_key: Key
    value: Decimal = Field(max_digits=14, decimal_places=4)


class EntryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Decimal | None = Field(default=None, max_digits=14, decimal_places=4)


class FeedbackIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period: Period
    text: Long


def _ind(e: PerformanceEntry) -> dict[str, Any]:
    return {
        "id": e.id,
        "period": e.period,
        "indicator_key": e.indicator_key,
        "label": e.label,
        "value": e.value,
        "unit": e.unit,
        "definition": e.definition,
        "published_at": e.published_at,
    }


def _published(org: uuid.UUID):  # type: ignore[no-untyped-def]
    return select(PerformanceEntry).where(
        PerformanceEntry.organization_id == org, PerformanceEntry.published_at.is_not(None)
    )


# ---------------------------------------------------------------- partner
class SummaryIndicatorOut(BaseModel):
    indicator_key: IndicatorKey
    label: str
    definition: str
    state: Literal["published", "unavailable"]  # unpublished data is never revealed
    period: str | None = None
    value: Decimal | None = None
    unit: str | None = None
    published_at: datetime | None = None


@partner.get(
    "/summary",
    response_model=ApiResponse[list[SummaryIndicatorOut]],
    responses=_ERR,
    summary="Both approved indicators: latest published value or state=unavailable",
)
def summary(ctx: PartnerDep, db: DbSession) -> ApiResponse[list[SummaryIndicatorOut]]:
    rows = db.execute(
        _published(ctx.organization_id).order_by(
            PerformanceEntry.indicator_key, PerformanceEntry.period.desc()
        )
    ).scalars()
    latest: dict[str, PerformanceEntry] = {}
    for e in rows:
        latest.setdefault(e.indicator_key, e)
    out = []
    for key in IndicatorKey:
        e = latest.get(key.value)
        out.append(
            SummaryIndicatorOut(
                indicator_key=key,
                label=LABELS[key],
                definition=DEFINITIONS[key],
                state="published" if e else "unavailable",
                period=e.period if e else None,
                value=e.value if e else None,
                unit=UNITS[key] if e else None,
                published_at=e.published_at if e else None,
            )
        )
    return ok(out)


@partner.get(
    "/trends",
    response_model=ApiResponse[list[IndicatorOut]],
    responses=_ERR,
    summary="Published series of one indicator, oldest first",
)
def trends(
    ctx: PartnerDep, db: DbSession, indicator: Annotated[Key, Query()]
) -> ApiResponse[list[IndicatorOut]]:
    rows = db.execute(
        _published(ctx.organization_id)
        .where(PerformanceEntry.indicator_key == indicator)
        .order_by(PerformanceEntry.period)
    ).scalars()
    return ok([IndicatorOut(**_ind(e)) for e in rows])


@partner.get(
    "/scorecards",
    response_model=ApiResponse[list[ScorecardOut]],
    responses=_ERR,
    summary="Published indicators grouped by period, newest first",
)
def scorecards(ctx: PartnerDep, db: DbSession) -> ApiResponse[list[ScorecardOut]]:
    rows = db.execute(
        _published(ctx.organization_id).order_by(
            PerformanceEntry.period.desc(), PerformanceEntry.indicator_key
        )
    ).scalars()
    grouped: dict[str, list[IndicatorOut]] = {}
    for e in rows:
        grouped.setdefault(e.period, []).append(IndicatorOut(**_ind(e)))
    return ok([ScorecardOut(period=p, indicators=i) for p, i in grouped.items()])


@partner.get("/feedback", response_model=ApiResponse[list[FeedbackOut]], responses=_ERR)
def partner_feedback(
    ctx: PartnerDep, db: DbSession, page: PageDep
) -> ApiResponse[list[FeedbackOut]]:
    base = select(PerformanceFeedback).where(
        PerformanceFeedback.organization_id == ctx.organization_id,
        PerformanceFeedback.published_at.is_not(None),
    )
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = db.execute(
        base.order_by(PerformanceFeedback.period.desc(), PerformanceFeedback.id)
        .limit(page.page_size)
        .offset(page.offset)
    ).scalars()
    return ok(
        [
            FeedbackOut(id=f.id, period=f.period, text=f.text, published_at=f.published_at)
            for f in rows
        ],
        meta=page_meta(page, total),
    )


def _cell(value: object) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


@partner.get(
    "/export.csv",
    response_class=Response,
    responses={**_ERR, 200: {"content": {"text/csv": {}}}},
    summary="CSV of your published indicators (formula-safe; PDF is not offered)",
)
def export_csv(ctx: PartnerDep, db: DbSession) -> Response:
    rows = db.execute(
        _published(ctx.organization_id).order_by(
            PerformanceEntry.period, PerformanceEntry.indicator_key
        )
    ).scalars()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["period", "indicator", "label", "value", "unit", "definition"])
    for e in rows:
        w.writerow(
            [_cell(v) for v in (e.period, e.indicator_key, e.label, e.value, e.unit, e.definition)]
        )
    return Response(
        buf.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="performance.csv"',
            "Cache-Control": "private, no-store",
        },
    )


# ------------------------------------------------------------------ staff
def _period_bounds(period: str) -> tuple[datetime, datetime]:
    year = int(period[:4])
    if len(period) == 4:
        start, end = (year, 1), (year + 1, 1)
    elif period[5] == "Q":
        q = int(period[6])
        start = (year, 3 * q - 2)
        end = (year, 3 * q + 1) if q < 4 else (year + 1, 1)
    else:
        month = int(period[5:7])
        if not 1 <= month <= 12:
            raise AppError("Invalid period", status_code=422, code="INVALID_PERIOD")
        start, end = (year, month), ((year, month + 1) if month < 12 else (year + 1, 1))
    return (
        datetime(start[0], start[1], 1, tzinfo=UTC),
        datetime(end[0], end[1], 1, tzinfo=UTC),
    )


class ComputeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period: Period


class ComputeResult(BaseModel):
    indicator_key: IndicatorKey
    state: Literal["available", "unavailable", "already_published"]
    value: Decimal | None = None
    reason: str | None = None
    entry_id: uuid.UUID | None = None


def _turnaround(db: Session, org: uuid.UUID, start: datetime, end: datetime) -> Decimal | None:
    span = PortalApplication.decided_at - PortalApplication.submitted_at
    avg = db.execute(
        select(func.avg(func.extract("epoch", span) / 86400)).where(
            PortalApplication.organization_id == org,
            PortalApplication.submitted_at.is_not(None),
            PortalApplication.decided_at >= start,
            PortalApplication.decided_at < end,
        )
    ).scalar_one()
    return None if avg is None else Decimal(str(round(float(avg), 2)))


def _completeness(db: Session, org: uuid.UUID) -> tuple[Decimal | None, str | None]:
    pathway = db.execute(
        select(PortalApplication.pathway)
        .where(
            PortalApplication.organization_id == org, PortalApplication.submitted_at.is_not(None)
        )
        .order_by(PortalApplication.submitted_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if pathway is None:
        return None, "the organisation has no submitted application, so its pathway is unknown"
    raw = cfg.get(db, f"required_documents.{pathway.value}")
    if not raw:
        return (
            None,
            f"required document categories for pathway {pathway.value} are not defined (D6)",
        )
    required = [c for c in raw.split(",") if c]
    accepted = set(
        db.execute(
            select(PartnerDocument.category)
            .join(
                PartnerDocumentVersion,
                (PartnerDocumentVersion.document_id == PartnerDocument.id)
                & (PartnerDocumentVersion.version_no == PartnerDocument.current_version_no),
            )
            .where(
                PartnerDocument.organization_id == org,
                PartnerDocument.status == DocStatus.ACTIVE,
                PartnerDocumentVersion.review_status == ReviewStatus.ACCEPTED,
                PartnerDocumentVersion.upload_status.in_(attachable_statuses()),
                or_(
                    PartnerDocumentVersion.expires_on.is_(None),
                    PartnerDocumentVersion.expires_on >= utcnow().date(),
                ),
            )
        ).scalars()
    )
    have = sum(1 for c in required if c in {a.value for a in accepted})
    return Decimal(str(round(have * 100 / len(required), 2))), None


@staff.post(
    "/organizations/{organization_id}/performance/compute",
    response_model=ApiResponse[list[ComputeResult]],
    responses=_ERR,
    summary="Calculate both approved indicators for a period as UNPUBLISHED entries",
)
def compute(
    organization_id: uuid.UUID, payload: ComputeIn, st: ReviewerDep, db: DbSession
) -> ApiResponse[list[ComputeResult]]:
    org = collab.require_org(db, st, organization_id)
    start, end = _period_bounds(payload.period)
    results: list[ComputeResult] = []
    for key in IndicatorKey:
        if key is IndicatorKey.APPLICATION_TURNAROUND_DAYS:
            value = _turnaround(db, org.id, start, end)
            reason = None if value is not None else "no application was decided in this period"
        else:
            value, reason = _completeness(db, org.id)
        if value is None:
            results.append(ComputeResult(indicator_key=key, state="unavailable", reason=reason))
            continue
        existing = db.execute(
            select(PerformanceEntry)
            .where(
                PerformanceEntry.organization_id == org.id,
                PerformanceEntry.period == payload.period,
                PerformanceEntry.indicator_key == key.value,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if existing is not None and existing.published_at is not None:
            results.append(
                ComputeResult(
                    indicator_key=key,
                    state="already_published",
                    value=existing.value,
                    entry_id=existing.id,
                    reason="unpublish it before recalculating",
                )
            )
            continue
        if existing is None:
            existing = PerformanceEntry(
                organization_id=org.id,
                period=payload.period,
                indicator_key=key.value,
                label=LABELS[key],
                unit=UNITS[key],
                definition=DEFINITIONS[key],
                created_by=st.user.id,
                value=value,
            )
            db.add(existing)
        existing.value = value
        db.flush()
        _audit(db, st, "performance", existing.id, "performance.computed", org.id)
        results.append(
            ComputeResult(indicator_key=key, state="available", value=value, entry_id=existing.id)
        )
    db.commit()
    return ok(results)


def _entry(db: Session, st: StaffContext, entry_id: uuid.UUID) -> PerformanceEntry:
    e = db.execute(
        select(PerformanceEntry)
        .where(
            PerformanceEntry.id == entry_id,
            collab.org_scope(st, PerformanceEntry.organization_id),
        )
        .with_for_update()
    ).scalar_one_or_none()
    if e is None:
        raise NotFoundError("Performance entry not found")
    return e


def _audit(
    db: Session, st: StaffContext, rtype: str, rid: uuid.UUID, action: str, org: uuid.UUID
) -> None:
    log_activity(
        db, rtype, rid, action, None, ActorType.STAFF, actor_user_id=st.user.id, organization_id=org
    )


def _staff_ind(e: PerformanceEntry) -> StaffIndicatorOut:
    return StaffIndicatorOut(
        **_ind(e), is_published=e.published_at is not None, organization_id=e.organization_id
    )


@staff.post(
    "/organizations/{organization_id}/performance",
    status_code=201,
    response_model=ApiResponse[StaffIndicatorOut],
    responses=_ERR,
    summary="Record an indicator value (unpublished until you publish it)",
)
def add_entry(
    organization_id: uuid.UUID, payload: EntryIn, st: ReviewerDep, db: DbSession
) -> ApiResponse[StaffIndicatorOut]:
    org = collab.require_org(db, st, organization_id)
    dup = db.execute(
        select(PerformanceEntry.id).where(
            PerformanceEntry.organization_id == org.id,
            PerformanceEntry.period == payload.period,
            PerformanceEntry.indicator_key == payload.indicator_key,
        )
    ).first()
    if dup:
        raise AppError(
            "Indicator already recorded for this period", status_code=409, code="DUPLICATE"
        )
    key = payload.indicator_key
    e = PerformanceEntry(
        organization_id=org.id,
        created_by=st.user.id,
        period=payload.period,
        indicator_key=key.value,
        label=LABELS[key],
        value=payload.value,
        unit=UNITS[key],
        definition=DEFINITIONS[key],
    )
    db.add(e)
    db.flush()
    _audit(db, st, "performance", e.id, "performance.recorded", org.id)
    db.commit()
    return ok(_staff_ind(e), "Recorded")


@staff.get(
    "/organizations/{organization_id}/performance",
    response_model=ApiResponse[list[StaffIndicatorOut]],
    responses=_ERR,
)
def list_entries(
    organization_id: uuid.UUID,
    st: ReviewerDep,
    db: DbSession,
    page: PageDep,
    period: Annotated[Period | None, Query()] = None,
    published: Annotated[bool | None, Query()] = None,
) -> ApiResponse[list[StaffIndicatorOut]]:
    org = collab.require_org(db, st, organization_id)
    base = select(PerformanceEntry).where(PerformanceEntry.organization_id == org.id)
    if period:
        base = base.where(PerformanceEntry.period == period)
    if published is not None:
        base = base.where(
            PerformanceEntry.published_at.is_not(None)
            if published
            else PerformanceEntry.published_at.is_(None)
        )
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = db.execute(
        base.order_by(PerformanceEntry.period.desc(), PerformanceEntry.indicator_key)
        .limit(page.page_size)
        .offset(page.offset)
    ).scalars()
    return ok([_staff_ind(e) for e in rows], meta=page_meta(page, total))


@staff.patch(
    "/performance/{entry_id}",
    response_model=ApiResponse[StaffIndicatorOut],
    responses=_ERR,
    summary="Edit an unpublished entry (unpublish first to correct a published one)",
)
def update_entry(
    entry_id: uuid.UUID, payload: EntryUpdate, st: ReviewerDep, db: DbSession
) -> ApiResponse[StaffIndicatorOut]:
    e = _entry(db, st, entry_id)
    if e.published_at is not None:
        raise AppError("Unpublish the entry before editing it", status_code=409, code="PUBLISHED")
    changes = payload.model_dump(exclude_unset=True)
    for required in ("value",):
        if required in changes and changes[required] is None:
            raise AppError(f"{required} cannot be cleared", status_code=422, code="REQUIRED_FIELD")
    for k, v in changes.items():
        setattr(e, k, v)
    _audit(db, st, "performance", e.id, "performance.updated", e.organization_id)
    db.commit()
    return ok(_staff_ind(e))


def _toggle(db: Session, st: StaffContext, entry_id: uuid.UUID, publish: bool) -> PerformanceEntry:
    e = _entry(db, st, entry_id)
    if publish and e.published_at is None:
        e.published_at, e.published_by = utcnow(), st.user.id
    elif not publish:
        e.published_at, e.published_by = None, None
    _audit(
        db,
        st,
        "performance",
        e.id,
        "performance.published" if publish else "performance.unpublished",
        e.organization_id,
    )
    db.commit()
    return e


@staff.post(
    "/performance/{entry_id}/publish", response_model=ApiResponse[StaffIndicatorOut], responses=_ERR
)
def publish_entry(
    entry_id: uuid.UUID, st: ReviewerDep, db: DbSession
) -> ApiResponse[StaffIndicatorOut]:
    return ok(_staff_ind(_toggle(db, st, entry_id, True)), "Published to partner")


@staff.post(
    "/performance/{entry_id}/unpublish",
    response_model=ApiResponse[StaffIndicatorOut],
    responses=_ERR,
)
def unpublish_entry(
    entry_id: uuid.UUID, st: ReviewerDep, db: DbSession
) -> ApiResponse[StaffIndicatorOut]:
    return ok(_staff_ind(_toggle(db, st, entry_id, False)), "Hidden from partner")


def _fb(f: PerformanceFeedback) -> StaffFeedbackOut:
    return StaffFeedbackOut(
        id=f.id,
        period=f.period,
        text=f.text,
        published_at=f.published_at,
        is_published=f.published_at is not None,
        organization_id=f.organization_id,
    )


@staff.post(
    "/organizations/{organization_id}/performance-feedback",
    status_code=201,
    response_model=ApiResponse[StaffFeedbackOut],
    responses=_ERR,
)
def add_feedback(
    organization_id: uuid.UUID, payload: FeedbackIn, st: ReviewerDep, db: DbSession
) -> ApiResponse[StaffFeedbackOut]:
    org = collab.require_org(db, st, organization_id)
    f = PerformanceFeedback(
        organization_id=org.id, period=payload.period, text=payload.text, created_by=st.user.id
    )
    db.add(f)
    db.flush()
    _audit(db, st, "performance_feedback", f.id, "performance.feedback_recorded", org.id)
    db.commit()
    return ok(_fb(f), "Recorded")


@staff.get(
    "/organizations/{organization_id}/performance-feedback",
    response_model=ApiResponse[list[StaffFeedbackOut]],
    responses=_ERR,
)
def list_feedback(
    organization_id: uuid.UUID, st: ReviewerDep, db: DbSession, page: PageDep
) -> ApiResponse[list[StaffFeedbackOut]]:
    org = collab.require_org(db, st, organization_id)
    base = select(PerformanceFeedback).where(PerformanceFeedback.organization_id == org.id)
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = db.execute(
        base.order_by(PerformanceFeedback.created_at.desc(), PerformanceFeedback.id)
        .limit(page.page_size)
        .offset(page.offset)
    ).scalars()
    return ok([_fb(f) for f in rows], meta=page_meta(page, total))


@staff.post(
    "/performance-feedback/{feedback_id}/{action}",
    response_model=ApiResponse[StaffFeedbackOut],
    responses=_ERR,
    summary="action is publish or unpublish",
)
def toggle_feedback(
    feedback_id: uuid.UUID, action: str, st: ReviewerDep, db: DbSession
) -> ApiResponse[StaffFeedbackOut]:
    if action not in ("publish", "unpublish"):
        raise NotFoundError("Unknown action")
    f = db.execute(
        select(PerformanceFeedback)
        .where(
            PerformanceFeedback.id == feedback_id,
            collab.org_scope(st, PerformanceFeedback.organization_id),
        )
        .with_for_update()
    ).scalar_one_or_none()
    if f is None:
        raise NotFoundError("Feedback not found")
    if action == "publish":
        f.published_at = f.published_at or utcnow()
        f.published_by = st.user.id
    else:
        f.published_at, f.published_by = None, None
    _audit(
        db, st, "performance_feedback", f.id, f"performance.feedback_{action}ed", f.organization_id
    )
    db.commit()
    return ok(_fb(f))
