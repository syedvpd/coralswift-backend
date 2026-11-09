"""Concurrency tests use separately committed connections (no shared test transaction).

They create uniquely named rows in the disposable *_test database and do not clean them up:
`activities` is append-only by design, and every test uses fresh organizations/users.
"""

import io
import threading
import uuid
from collections.abc import Callable
from typing import Any, cast

from fastapi import UploadFile
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session
from starlette.datastructures import Headers

from app.common.utilities import utcnow
from app.core.config import Settings
from app.core.exceptions import AppError
from app.modules.applications import service as app_service
from app.modules.applications.constants import PortalStatus
from app.modules.applications.models import ApplicationSubmission, PortalApplication
from app.modules.applications.transitions import Actor
from app.modules.auth.constants import StaffRole, UserStatus, UserType
from app.modules.auth.dependencies import PartnerContext, StaffContext
from app.modules.auth.models import AuthSession, User
from app.modules.auth.service import create_staff_user
from app.modules.notifications.constants import NotificationType, TemplateKey
from app.modules.notifications.models import Notification
from app.modules.notifications.service import queue_notification
from app.modules.organizations.constants import MembershipRole
from app.modules.organizations.models import PartnerMembership, PartnerOrganization
from app.modules.partner_documents import service as doc_service
from app.modules.partner_documents.constants import PartnerDocCategory
from app.modules.partner_documents.models import PartnerDocument, PartnerDocumentVersion
from app.modules.partners.constants import EngagementPathway
from tests import factories
from tests.conftest import ROOT  # noqa: F401
from tests.fakes import InMemoryStorage
from tests.helpers import FULL_PROFILE, PASSWORD, REQUIRED_DOCS  # noqa: F401


def run_parallel(n: int, fn: Callable[[int], Any]) -> list[Any]:
    results: list[Any] = [None] * n
    barrier = threading.Barrier(n)

    def worker(i: int) -> None:
        barrier.wait()
        try:
            results[i] = fn(i)
        except AppError as exc:
            results[i] = exc

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


def make_partner(engine: Engine) -> tuple[PartnerContext, uuid.UUID]:
    suffix = uuid.uuid4().hex[:8]
    with Session(engine, expire_on_commit=False) as s:
        org = PartnerOrganization(legal_name=f"Conc {suffix}")
        user = User(
            email=f"conc-{suffix}@example.com",
            full_name="Conc",
            user_type=UserType.PARTNER,
            status=UserStatus.ACTIVE,
            password_hash="x",
        )
        s.add_all([org, user])
        s.flush()
        s.add(PartnerMembership(organization_id=org.id, user_id=user.id))
        profile = dict(FULL_PROFILE)
        profile["country"] = "IN"
        for key in (
            "registration_number",
            "year_established",
            "employee_count",
            "registered_address",
            "country",
            "website",
            "technical_capabilities",
            "infrastructure_summary",
            "business_description",
            "service_categories",
            "client_references",
            "authorized_contacts",
        ):
            setattr(org, key, profile[key])
        org.annual_turnover_inr_crore = 5  # type: ignore[assignment]
        for cat in REQUIRED_DOCS:
            doc = PartnerDocument(
                organization_id=org.id, category=PartnerDocCategory(cat), current_version_no=1
            )
            s.add(doc)
            s.flush()
            s.add(
                PartnerDocumentVersion(
                    document_id=doc.id,
                    version_no=1,
                    storage_key=f"partners/portal/t/{uuid.uuid4().hex}.pdf",
                    original_filename="a.pdf",
                    content_type="application/pdf",
                    file_size=10,
                    checksum="0" * 64,
                    upload_status="quarantined",
                    uploaded_by=user.id,
                    uploaded_at=utcnow(),
                )
            )
        s.commit()
        ctx = PartnerContext(
            user=user,
            session=cast(AuthSession, None),
            organization_id=org.id,
            role=MembershipRole.OWNER,
        )
        return ctx, org.id


def test_concurrent_submissions_create_exactly_one_submission(
    concurrency_engine: Engine, settings: Settings
) -> None:
    ctx, _ = make_partner(concurrency_engine)
    with Session(concurrency_engine, expire_on_commit=False) as s:
        app_id = app_service.create_draft(
            s, ctx, EngagementPathway.DIRECT_PROJECT_ENGAGEMENT, None
        ).id

    def submit(_: int) -> str:
        with Session(concurrency_engine, expire_on_commit=False) as s:
            return app_service.submit(s, settings, ctx, app_id).status.value

    results = run_parallel(4, submit)
    assert results.count("submitted") == 1
    assert all(
        isinstance(r, AppError) and r.code == "INVALID_TRANSITION"
        for r in results
        if r != "submitted"
    )
    with Session(concurrency_engine, expire_on_commit=False) as s:
        assert (
            s.execute(
                select(func.count())
                .select_from(ApplicationSubmission)
                .where(ApplicationSubmission.application_id == app_id)
            ).scalar_one()
            == 1
        )


def test_duplicate_open_application_race_has_one_winner(concurrency_engine: Engine) -> None:
    ctx, _ = make_partner(concurrency_engine)

    def create(_: int) -> str:
        with Session(concurrency_engine, expire_on_commit=False) as s:
            return str(
                app_service.create_draft(s, ctx, EngagementPathway.VENDOR_SUBCONTRACTING, None).id
            )

    results = run_parallel(4, create)
    winners = [r for r in results if isinstance(r, str)]
    assert len(winners) == 1
    assert all(
        isinstance(r, AppError) and r.code == "APPLICATION_ALREADY_OPEN"
        for r in results
        if not isinstance(r, str)
    )


def test_concurrent_reviewer_decisions_apply_once(
    concurrency_engine: Engine, settings: Settings
) -> None:
    ctx, org_id = make_partner(concurrency_engine)
    with Session(concurrency_engine, expire_on_commit=False) as s:
        reviewers = [
            create_staff_user(
                s,
                settings,
                email=f"rev-{uuid.uuid4().hex[:8]}@example.com",
                full_name="R",
                role=StaffRole.PARTNER_REVIEWER,
                password=PASSWORD,
            )
            for _ in range(2)
        ]
        s.commit()
        app = app_service.create_draft(s, ctx, EngagementPathway.DIRECT_PROJECT_ENGAGEMENT, None)
        app_id = app.id
        row = s.get(PortalApplication, app_id)
        assert row is not None
        row.status = PortalStatus.ELIGIBILITY_VERIFICATION
        row.assigned_reviewer_id = reviewers[0].id
        from app.modules.applications.constants import VerificationOutcome
        from app.modules.applications.models import EligibilityVerification

        s.add(
            EligibilityVerification(
                application_id=app_id,
                submission_no=1,
                verified_by=reviewers[0].id,
                verified_at=utcnow(),
                outcome=VerificationOutcome.VERIFIED,
                supporting_version_ids=[],
            )
        )
        s.commit()
        reviewer_ids = [r.id for r in reviewers]

    def decide(i: int) -> str:
        with Session(concurrency_engine, expire_on_commit=False) as s:
            user = s.get(User, reviewer_ids[i])
            assert user is not None
            app = app_service.lock_application(s, app_id)
            app_service.transition(
                s,
                settings,
                app=app,
                target=PortalStatus.CAPABILITY_REVIEW,
                actor=Actor.REVIEWER,
                user=user,
            )
            s.commit()
            return "advanced"

    results = run_parallel(2, decide)
    assert results.count("advanced") == 1
    assert sum(isinstance(r, AppError) and r.code == "INVALID_TRANSITION" for r in results) == 1
    with Session(concurrency_engine, expire_on_commit=False) as s:
        assert s.get(PortalApplication, app_id).status is PortalStatus.CAPABILITY_REVIEW  # type: ignore[union-attr]


def test_concurrent_document_replacement_keeps_versions_consistent(
    concurrency_engine: Engine, settings: Settings
) -> None:
    ctx, org_id = make_partner(concurrency_engine)
    storage = InMemoryStorage()
    with Session(concurrency_engine, expire_on_commit=False) as s:
        doc_id = s.execute(
            select(PartnerDocument.id).where(PartnerDocument.organization_id == org_id).limit(1)
        ).scalar_one()

    def replace(_: int) -> int:
        upload = UploadFile(
            io.BytesIO(factories.PDF),
            filename="v.pdf",
            headers=Headers({"content-type": "application/pdf"}),
        )
        with Session(concurrency_engine, expire_on_commit=False) as s:
            return doc_service.replace(
                s, storage, settings, ctx, doc_id, upload=upload, expires_on=None
            )[1].version_no

    results = run_parallel(4, replace)
    assert sorted(results) == [2, 3, 4, 5]  # unique, gap-free numbers
    with Session(concurrency_engine, expire_on_commit=False) as s:
        assert s.get(PartnerDocument, doc_id).current_version_no == 5  # type: ignore[union-attr]
        assert len(storage.objects) == 4


def test_duplicate_notification_generation_is_deduplicated(concurrency_engine: Engine) -> None:
    key = f"dup-test:{uuid.uuid4()}"

    def queue(_: int) -> None:
        with Session(concurrency_engine, expire_on_commit=False) as s:
            queue_notification(
                s,
                recipient="dup@example.com",
                kind=NotificationType.APPLICATION,
                template=TemplateKey.APPLICATION_STATUS_CHANGED,
                context={"reference": "R"},
                dedupe_key=key,
            )
            s.commit()

    run_parallel(6, queue)
    with Session(concurrency_engine, expire_on_commit=False) as s:
        assert (
            s.execute(
                select(func.count()).select_from(Notification).where(Notification.dedupe_key == key)
            ).scalar_one()
            == 1
        )


def test_concurrent_refresh_token_use_allows_one_rotation(
    concurrency_engine: Engine, settings: Settings
) -> None:
    from app.modules.auth import service as auth_service

    suffix = uuid.uuid4().hex[:8]
    with Session(concurrency_engine, expire_on_commit=False) as s:
        user = create_staff_user(
            s,
            settings,
            email=f"rot-{suffix}@example.com",
            full_name="R",
            role=StaffRole.PARTNER_REVIEWER,
            password=PASSWORD,
        )
        s.commit()
        pair, _ = auth_service.login(
            s, settings, email=user.email, password=PASSWORD, ip="1.1.1.1", user_agent="t"
        )
        refresh = pair.refresh_token

    def rotate(_: int) -> str:
        with Session(concurrency_engine, expire_on_commit=False) as s:
            return auth_service.refresh_session(s, settings, refresh).refresh_token

    results = run_parallel(3, rotate)
    assert sum(isinstance(r, str) for r in results) == 1
    assert all(isinstance(r, AppError) for r in results if not isinstance(r, str))
    with Session(concurrency_engine, expire_on_commit=False) as s:
        sessions = (
            s.execute(select(AuthSession).where(AuthSession.user_id == user.id)).scalars().all()
        )
        assert len(sessions) == 1
    assert StaffContext is not None
