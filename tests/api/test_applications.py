from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.applications.models import ApplicationStatusHistory, ApplicationSubmission
from app.modules.notifications.models import Notification
from tests.fakes import RecordingEmail
from tests.helpers import complete_partner, create_draft, onboard_partner, submitted_application

A = "/api/v1/partner/applications"


def test_requires_login(client: TestClient) -> None:
    assert client.get(A).status_code == 401
    assert client.post(A, json={"pathway": "vendor_subcontracting"}).status_code == 401


def test_draft_lifecycle_and_duplicate_guard(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    p = onboard_partner(client, db, settings, email)
    app_id = create_draft(client, p)
    got = client.get(f"{A}/{app_id}", headers=p.headers).json()["data"]
    assert got["status"] == "draft" and got["reference"].startswith("CS-APP-")
    dup = client.post(A, headers=p.headers, json={"pathway": "vendor_subcontracting"})
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "APPLICATION_ALREADY_OPEN"
    upd = client.patch(
        f"{A}/{app_id}",
        headers=p.headers,
        json={"cover_note": "Hello", "pathway": "vendor_subcontracting"},
    )
    assert (
        upd.json()["data"]["cover_note"] == "Hello"
        and upd.json()["data"]["pathway"] == "vendor_subcontracting"
    )
    # partners can never set status or other privileged fields
    for body in (
        {"status": "approved"},
        {"status": "capability_review"},
        {"assigned_reviewer_id": "x"},
    ):
        assert client.patch(f"{A}/{app_id}", headers=p.headers, json=body).status_code == 422
    assert client.post(A, headers=p.headers, json={"pathway": "bogus"}).status_code == 422


def test_submit_requires_complete_profile_and_documents(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    p = onboard_partner(client, db, settings, email)
    app_id = create_draft(client, p)
    r = client.post(f"{A}/{app_id}/submit", headers=p.headers)
    assert r.status_code == 422 and r.json()["error"]["code"] == "APPLICATION_INCOMPLETE"
    details = {d["field"]: d["missing"] for d in r.json()["error"]["details"]}
    assert "registration_number" in details["profile"] and len(details["documents"]) == 7
    complete_partner(client, p, docs=False)
    ready = client.get(f"{A}/{app_id}/readiness", headers=p.headers).json()["data"]
    assert ready["missing_profile_fields"] == [] and len(ready["missing_document_categories"]) == 7
    assert client.post(f"{A}/{app_id}/submit", headers=p.headers).status_code == 422


def test_submit_snapshot_history_and_notifications(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    p = onboard_partner(client, db, settings, email)
    app_id = submitted_application(client, p)
    got = client.get(f"{A}/{app_id}", headers=p.headers).json()["data"]
    assert got["status"] == "submitted" and got["submission_count"] == 1 and got["submitted_at"]
    snap = db.execute(select(ApplicationSubmission)).scalar_one()
    assert snap.submission_no == 1 and len(snap.snapshot["documents"]) == 7
    assert snap.snapshot["profile"]["registration_number"] == "U72200TG2015PTC123456"
    hist = client.get(f"{A}/{app_id}/history", headers=p.headers).json()["data"]
    assert [h["to_status"] for h in hist] == ["draft", "submitted"]
    keys = set(db.execute(select(Notification.template_key)).scalars())
    assert {t.value for t in keys} >= {"application_submitted", "internal_new_enquiry"}
    assert any(m.to == p.email and "submitted" in m.subject for m in email.sent)
    # a second submit is an invalid transition, not a duplicate record
    again = client.post(f"{A}/{app_id}/submit", headers=p.headers)
    assert again.status_code == 409 and again.json()["error"]["code"] == "INVALID_TRANSITION"
    assert db.execute(select(func.count()).select_from(ApplicationSubmission)).scalar_one() == 1


def test_withdraw_then_new_application_allowed(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    p = onboard_partner(client, db, settings, email)
    app_id = submitted_application(client, p)
    r = client.post(f"{A}/{app_id}/withdraw", headers=p.headers, json={"note": "Changed plans"})
    assert r.status_code == 200 and r.json()["data"]["status"] == "withdrawn"
    assert client.post(f"{A}/{app_id}/withdraw", headers=p.headers, json={}).status_code == 409
    assert client.post(f"{A}/{app_id}/submit", headers=p.headers).status_code == 409
    assert create_draft(client, p)
    rows = db.execute(select(ApplicationStatusHistory.to_status)).scalars().all()
    assert [r.value for r in rows].count("withdrawn") == 1
