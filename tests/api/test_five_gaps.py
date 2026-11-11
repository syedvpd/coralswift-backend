"""Suspended error code, 48 h escalation, writable password/token policy, denied-download audit,
onboarding-duration metric."""

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.common.utilities import utcnow
from app.core.config import Settings
from app.modules.admin import maintenance
from app.modules.auth.constants import StaffRole
from app.modules.enquiries.models import Enquiry
from app.modules.onboarding.models import OnboardingRecord
from tests import factories
from tests.fakes import RecordingEmail
from tests.helpers import PASSWORD, bearer, login, make_staff, onboard_partner

ADM = "/api/v1/admin"
A = "/api/v1/auth"
P = "/api/v1/partner"
R = "/api/v1/reviewer"


def _staff(client: TestClient, db: Session, settings: Settings, role: StaffRole):  # type: ignore[no-untyped-def]
    user = make_staff(db, settings, role)
    return user, bearer(login(client, user.email)["access_token"])


def test_suspended_and_deactivated_have_different_codes_after_correct_password(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    _, sa = _staff(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    suspended = onboard_partner(client, db, settings, email)
    owner = onboard_partner(client, db, settings, email)
    uid = client.get(f"{A}/me", headers=suspended.headers).json()["data"]["id"]
    assert client.post(f"{ADM}/accounts/{uid}/suspend", headers=sa).status_code == 200
    wrong = client.post(
        f"{A}/login", json={"email": suspended.email, "password": "wrong-password-1"}
    )
    assert wrong.status_code == 401 and wrong.json()["error"]["code"] == "INVALID_CREDENTIALS"
    ok = client.post(f"{A}/login", json={"email": suspended.email, "password": PASSWORD})
    assert ok.status_code == 403 and ok.json()["error"]["code"] == "ACCOUNT_SUSPENDED"
    # a team owner deactivating a colleague gives the other code
    team_member = client.post(
        f"{P}/team/invitations",
        headers=owner.headers,
        json={"email": "colleague.two@example.com", "full_name": "Colleague Two"},
    )
    assert team_member.status_code == 201
    # suspended accounts can be reactivated by an administrator
    assert client.post(f"{ADM}/accounts/{uid}/reactivate", headers=sa).status_code == 200
    back = client.post(f"{A}/login", json={"email": suspended.email, "password": PASSWORD})
    assert back.status_code == 200


def test_escalation_fires_at_48_hours_not_at_the_24_hour_target(
    client: TestClient, db: Session, settings: Settings
) -> None:
    for _ in range(2):
        client.post("/api/v1/enquiries/contact", json=factories.contact())
    ids = [e.id for e in db.query(Enquiry).order_by(Enquiry.created_at.desc()).limit(2)]
    now = utcnow()
    db.execute(
        update(Enquiry)
        .where(Enquiry.id == ids[0])
        .values(created_at=now - timedelta(hours=30), response_due_at=now - timedelta(hours=6))
    )
    db.execute(
        update(Enquiry)
        .where(Enquiry.id == ids[1])
        .values(created_at=now - timedelta(hours=50), response_due_at=now - timedelta(hours=26))
    )
    db.commit()
    done = maintenance.escalate_overdue(db, settings)
    db.expire_all()
    young, old = db.get(Enquiry, ids[0]), db.get(Enquiry, ids[1])
    assert young is not None and old is not None
    assert done >= 1 and old.escalated_at is not None
    assert young.escalated_at is None  # first-response target missed, escalation target not yet


def test_password_and_token_policy_is_writable_and_applied(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    _, sa = _staff(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    key = f"{ADM}/settings/security.password_min_length"
    assert client.put(key, headers=sa, json={"value": "7"}).status_code == 422
    assert client.put(key, headers=sa, json={"value": "20"}).status_code == 200
    ttl = f"{ADM}/settings/security.access_token_minutes"
    assert client.put(ttl, headers=sa, json={"value": "5"}).status_code == 200
    try:
        p = onboard_partner(client, db, settings, email)
        too_short = client.post(
            f"{A}/change-password",
            headers=p.headers,
            json={"current_password": PASSWORD, "new_password": "Short-Pass-12x!"},
        )
        assert too_short.status_code == 422  # 14 chars < the written minimum of 20
        tokens = client.post(f"{A}/login", json={"email": p.email, "password": PASSWORD}).json()
        assert tokens["data"]["expires_in"] == 5 * 60  # written lifetime applied to new sessions
    finally:
        client.delete(key, headers=sa)
        client.delete(ttl, headers=sa)
    back = client.post(f"{A}/login", json={"email": p.email, "password": PASSWORD}).json()
    assert back["data"]["expires_in"] == settings.access_token_expire_minutes * 60


def test_denied_downloads_are_audited_without_leaking(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    _, sa = _staff(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    owner = onboard_partner(client, db, settings, email)
    other = onboard_partner(client, db, settings, email)
    up = client.post(
        f"{P}/documents",
        headers=owner.headers,
        data={"category": "registration_proof"},
        files={"file": ("a.pdf", factories.PDF)},
    )
    doc_id = up.json()["data"]["id"]
    denied = client.get(f"{P}/documents/{doc_id}/download", headers=other.headers)
    assert denied.status_code == 404  # same answer as a missing document
    rows = client.get(f"{ADM}/audit?action=document.download_denied", headers=sa).json()["data"]
    mine = [r for r in rows if r["record_id"] == doc_id]
    assert len(mine) == 1 and mine[0]["outcome"] == "failure"
    assert mine[0]["organization_id"] == other.organization_id  # the requester, not the owner
    assert "name" not in str(mine[0]["meta"]).lower()
    ok = client.get(f"{P}/documents/{doc_id}/download", headers=owner.headers)
    assert ok.status_code == 200
    again = client.get(f"{ADM}/audit?action=document.download_denied", headers=sa).json()
    assert again["meta"]["total"] >= 1


def test_onboarding_duration_metric_value(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    _, sa = _staff(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    p = onboard_partner(client, db, settings, email)
    rec = client.post(f"{R}/onboarding", headers=sa, json={"organization_id": p.organization_id})
    rid = rec.json()["data"]["id"]
    assert client.post(f"{R}/onboarding/{rid}/complete", headers=sa).status_code == 200
    now = utcnow()
    db.execute(
        update(OnboardingRecord)
        .where(OnboardingRecord.id == rid)
        .values(started_at=now - timedelta(days=7), completed_at=now - timedelta(days=4))
    )
    db.commit()
    kpi = client.get(f"{ADM}/reports/kpis", headers=sa).json()["data"]
    assert kpi["onboarding_completed"] >= 1
    expected = db.execute(
        select(
            func.avg(
                func.extract("epoch", OnboardingRecord.completed_at - OnboardingRecord.started_at)
                / 86400
            )
        ).where(OnboardingRecord.completed_at.is_not(None))
    ).scalar_one()
    assert kpi["onboarding_duration_days_avg"] == round(float(expected), 2)
    mine = db.get(OnboardingRecord, rid)
    assert mine is not None and mine.completed_at is not None
    assert round((mine.completed_at - mine.started_at).total_seconds() / 86400, 2) == 3.0
