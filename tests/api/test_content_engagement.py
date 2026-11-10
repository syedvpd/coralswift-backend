"""Content CMS, meetings, newsletter, privacy tests. NOT executed yet."""

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.admin import maintenance
from app.modules.auth.constants import StaffRole
from app.modules.content.models import ContentItem
from app.modules.engagement.models import MeetingRequest
from app.modules.enquiries.models import Activity
from tests import factories
from tests.fakes import InMemoryStorage, RecordingEmail
from tests.helpers import last_token, make_staff, staff_headers

AC = "/api/v1/admin/content"
PC = "/api/v1/content"


def staff(client: TestClient, db: Session, settings: Settings, role: StaffRole) -> dict[str, str]:
    return staff_headers(client, make_staff(db, settings, role))


def new_item(
    client: TestClient, h: dict[str, str], slug: str = "partner-criteria", **o: Any
) -> str:
    body = {
        "slug": slug,
        "content_type": "faq",
        "title": "What are the proposed criteria?",
        "summary": "Proposed screening criteria",
        "body": "Three years, fifty personnel.",
        "category": "partnerships",
        "tags": ["criteria", "partners"],
        **o,
    }
    r = client.post(AC, headers=h, json=body)
    assert r.status_code == 201, r.text
    return str(r.json()["data"]["id"])


def test_content_workflow_and_public_visibility(
    client: TestClient, db: Session, settings: Settings
) -> None:
    ca = staff(client, db, settings, StaffRole.CONTENT_ADMINISTRATOR)
    sa = staff(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    item = new_item(client, ca)
    assert client.get(PC, headers={}).json()["data"] == []  # drafts are never public
    assert client.get(f"{PC}/partner-criteria").status_code == 404
    assert client.post(f"{AC}/{item}/publish", headers=ca).status_code == 409  # not approved
    assert client.post(f"{AC}/{item}/submit", headers=ca).status_code == 200
    assert client.post(f"{AC}/{item}/approve", headers=ca, json={}).status_code == 403  # SA only
    assert (
        client.patch(f"{AC}/{item}", headers=ca, json={"title": "x"}).status_code == 409
    )  # not a draft
    approved = client.post(f"{AC}/{item}/approve", headers=sa, json={"note": "ok"}).json()["data"]
    assert (
        approved["status"] == "approved"
        and approved["reviewer_id"]
        and approved["last_reviewed_at"]
    )
    assert client.get(f"{PC}/partner-criteria").status_code == 404  # approved is still not live
    assert client.post(f"{AC}/{item}/publish", headers=ca).json()["data"]["status"] == "published"
    pub = client.get(f"{PC}/partner-criteria")
    assert (
        pub.status_code == 200
        and "owner_id" not in pub.text
        and pub.headers["cache-control"] == "public, max-age=300"
    )
    assert client.get(f"{PC}?q=fifty").json()["meta"]["total"] == 1
    assert client.get(f"{PC}?q=%25").json()["data"] == []
    assert client.get(f"{PC}?type=article").json()["data"] == []
    assert client.get(f"{PC}?tag=criteria").json()["meta"]["total"] == 1
    assert [s["slug"] for s in client.get(f"{PC}/sitemap").json()["data"]] == ["partner-criteria"]
    other = new_item(client, ca, slug="review-process", tags=["partners"])
    client.post(f"{AC}/{other}/submit", headers=ca)
    client.post(f"{AC}/{other}/approve", headers=sa, json={})
    client.post(f"{AC}/{other}/publish", headers=ca)
    rel = client.get(f"{PC}/partner-criteria").json()["data"]["related"]
    assert [r["slug"] for r in rel] == ["review-process"]
    # editing live content requires reopening, which removes it from the site
    assert client.post(f"{AC}/{item}/reopen", headers=ca).json()["data"]["status"] == "draft"
    assert client.get(f"{PC}/partner-criteria").status_code == 404
    client.patch(f"{AC}/{item}", headers=ca, json={"body": "Updated body"})
    versions = client.get(f"{AC}/{item}/versions", headers=ca).json()["data"]
    assert [v["version_no"] for v in versions] == [2, 1]
    assert "content.published" in set(db.execute(select(Activity.action)).scalars())


def test_scheduled_content_contract_and_maintenance_publish(
    client: TestClient, db: Session, settings: Settings
) -> None:
    ca = staff(client, db, settings, StaffRole.CONTENT_ADMINISTRATOR)
    sa = staff(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    item_id = new_item(client, ca, slug="scheduled-guide")
    client.post(f"{AC}/{item_id}/submit", headers=ca)
    client.post(f"{AC}/{item_id}/approve", headers=sa, json={})
    schedule_url = f"{AC}/{item_id}/schedule"
    when = datetime.now(UTC) + timedelta(minutes=5)
    scheduled = client.post(schedule_url, headers=ca, json={"publish_at": when.isoformat()})
    assert scheduled.status_code == 200
    assert scheduled.json()["data"]["scheduled_publish_at"]
    assert client.get(f"{PC}/scheduled-guide").status_code == 404
    cancelled = client.delete(schedule_url, headers=ca)
    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["scheduled_publish_at"] is None
    naive = client.post(schedule_url, headers=ca, json={"publish_at": "2030-01-01T00:00:00"})
    assert naive.status_code == 422

    item = db.get(ContentItem, item_id)
    assert item is not None
    item.scheduled_publish_at = datetime.now(UTC) - timedelta(seconds=1)
    db.flush()
    assert maintenance.publish_scheduled_content(db) == 1
    assert client.get(f"{PC}/scheduled-guide").status_code == 200


def test_content_rejection_slug_conflict_and_permissions(
    client: TestClient, db: Session, settings: Settings
) -> None:
    ca = staff(client, db, settings, StaffRole.CONTENT_ADMINISTRATOR)
    sa = staff(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    bdm = staff(client, db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
    item = new_item(client, ca)
    assert (
        client.post(
            AC,
            headers=ca,
            json={"slug": "partner-criteria", "content_type": "page", "title": "t", "body": "b"},
        ).status_code
        == 409
    )
    assert (
        client.post(
            AC,
            headers=ca,
            json={"slug": "Bad Slug", "content_type": "page", "title": "t", "body": "b"},
        ).status_code
        == 422
    )
    assert client.get(AC, headers=bdm).status_code == 403
    client.post(f"{AC}/{item}/submit", headers=ca)
    assert (
        client.post(f"{AC}/{item}/reject", headers=sa, json={"note": "Needs sources"}).json()[
            "data"
        ]["review_note"]
        == "Needs sources"
    )
    assert client.get(f"{AC}/{item}", headers=ca).json()["data"]["status"] == "draft"


def test_content_attachment_download(
    client: TestClient, db: Session, settings: Settings, storage: InMemoryStorage
) -> None:
    ca = staff(client, db, settings, StaffRole.CONTENT_ADMINISTRATOR)
    sa = staff(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    item = new_item(client, ca, slug="capability-statement", content_type="resource")
    r = client.post(
        f"{AC}/{item}/attachment",
        headers=ca,
        data={"version_label": "2026-11"},
        files={"file": ("cap.pdf", factories.PDF, "application/pdf")},
    )
    assert r.status_code == 200 and r.json()["data"]["attachment"]["version_label"] == "2026-11"
    bad = client.post(
        f"{AC}/{item}/attachment",
        headers=ca,
        files={"file": ("x.exe", b"MZ" + b"0" * 30, "application/octet-stream")},
    )
    assert bad.status_code == 415
    assert client.get(f"{PC}/capability-statement/download").status_code == 404  # unpublished
    client.post(f"{AC}/{item}/submit", headers=ca)
    client.post(f"{AC}/{item}/approve", headers=sa, json={})
    client.post(f"{AC}/{item}/publish", headers=ca)
    dl = client.get(f"{PC}/capability-statement/download")
    assert dl.status_code == 200 and dl.content == factories.PDF
    assert (
        client.post(
            f"{AC}/{item}/attachment",
            headers=ca,
            files={"file": ("c.pdf", factories.PDF, "application/pdf")},
        ).status_code
        == 409
    )


def slot(days: int = 3) -> dict[str, str]:
    start = datetime.now(UTC) + timedelta(days=days)
    return {"start": start.isoformat(), "end": (start + timedelta(minutes=30)).isoformat()}


def test_meeting_request_and_manual_confirmation(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    body = factories.submitter(
        purpose="Introduce our ERP needs",
        preferred_slots=[slot(3), slot(4)],
        timezone="America/New_York",
    )
    r = client.post("/api/v1/meetings", json=body)
    assert r.status_code == 201
    ref = r.json()["data"]["reference_number"]
    assert any("meeting request" in m.subject for m in email.sent if m.to == "asha.rao@example.com")
    assert all(
        "confirmed" not in m.text.lower() or "not confirmed" in m.text.lower() for m in email.sent
    )
    bad_cases: tuple[dict[str, Any], ...] = (
        {"timezone": "Mars/Base"},
        {"preferred_slots": []},
        {"preferred_slots": [{"start": "2020-01-01T10:00:00Z", "end": "2020-01-01T11:00:00Z"}]},
        {"privacy_consent": False},
    )
    for bad in bad_cases:
        assert client.post("/api/v1/meetings", json={**body, **bad}).status_code == 422
    bdm = staff(client, db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
    rows = client.get("/api/v1/admin/enquiries?type=meeting", headers=bdm).json()["data"]
    eid = next(r["id"] for r in rows if r["reference_number"] == ref)
    start = (datetime.now(UTC) + timedelta(days=3)).replace(microsecond=0)
    payload = {
        "start": start.isoformat(),
        "end": (start + timedelta(minutes=30)).isoformat(),
        "calendar_checked": False,
    }
    assert (
        client.post(f"/api/v1/admin/meetings/{eid}/confirm", headers=bdm, json=payload).status_code
        == 422
    )
    ok = client.post(
        f"/api/v1/admin/meetings/{eid}/confirm",
        headers=bdm,
        json={**payload, "calendar_checked": True},
    )
    assert ok.status_code == 200
    m = db.execute(select(MeetingRequest)).scalar_one()
    assert m.status.value == "confirmed" and m.calendar_checked
    assert any("Confirmed" in m2.subject for m2 in email.sent if m2.to == "asha.rao@example.com")
    assert (
        client.post(
            f"/api/v1/admin/meetings/{eid}/confirm",
            headers=bdm,
            json={**payload, "calendar_checked": True},
        ).status_code
        == 409
    )
    detail = client.get(f"/api/v1/admin/enquiries/{eid}", headers=bdm).json()["data"]["details"]
    assert detail["status"] == "confirmed"


def test_meeting_db_forbids_confirmation_without_calendar_check(
    client: TestClient, db: Session
) -> None:
    import pytest
    from sqlalchemy.exc import IntegrityError

    from app.modules.engagement.models import MeetingStatus

    body = factories.submitter(purpose="Intro", preferred_slots=[slot()], timezone="Europe/London")
    assert client.post("/api/v1/meetings", json=body).status_code == 201
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(update(MeetingRequest).values(status=MeetingStatus.CONFIRMED))
        db.flush()


def test_newsletter_and_privacy_requests(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    assert (
        client.post(
            "/api/v1/newsletter/subscribe", json={"email": "reader@example.com", "consent": False}
        ).status_code
        == 422
    )
    token = client.post(
        "/api/v1/newsletter/subscribe", json={"email": "Reader@Example.com", "consent": True}
    ).json()["data"]["unsubscribe_token"]
    client.post(
        "/api/v1/newsletter/subscribe", json={"email": "reader@example.com", "consent": True}
    )  # idempotent
    sa = staff(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    csv_text = client.get("/api/v1/admin/reports/newsletter.csv", headers=sa).text
    assert csv_text.count("reader@example.com") == 1 and "subscribed" in csv_text
    assert (
        client.post(
            "/api/v1/newsletter/unsubscribe",
            json={"email": "reader@example.com", "token": "wrong-token-value"},
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/v1/newsletter/unsubscribe", json={"email": "reader@example.com", "token": token}
        ).status_code
        == 200
    )
    r = client.post(
        "/api/v1/privacy/requests",
        json={
            "email": "subject@example.com",
            "kind": "deletion",
            "details": "Please delete my data",
        },
    )
    assert r.status_code == 201 and r.json()["data"]["reference"].startswith("PR-")
    assert any("privacy request" in m.subject for m in email.sent if m.to == "subject@example.com")
    rows = client.get("/api/v1/admin/privacy-requests", headers=sa).json()["data"]
    assert rows[0]["status"] == "received" and rows[0]["email_verified"] is False
    blocked = client.post(
        f"/api/v1/admin/privacy-requests/{rows[0]['id']}",
        headers=sa,
        json={"status": "completed", "resolution_note": "too early"},
    )
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "EMAIL_NOT_VERIFIED"
    token = last_token(email, "subject@example.com")
    verified = client.post("/api/v1/privacy/requests/verify", json={"token": token})
    assert (
        verified.status_code == 200
        and verified.json()["data"]["reference"] == r.json()["data"]["reference"]
    )
    again = client.post("/api/v1/privacy/requests/verify", json={"token": token})
    assert again.status_code == 400  # single use
    done = client.post(
        f"/api/v1/admin/privacy-requests/{rows[0]['id']}",
        headers=sa,
        json={"status": "completed", "resolution_note": "Deleted manually"},
    )
    assert done.json()["data"]["status"] == "completed"
    bdm = staff(client, db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
    assert client.get("/api/v1/admin/privacy-requests", headers=bdm).status_code == 403
