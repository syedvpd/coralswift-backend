"""Settings, templates, MFA reset, KPIs, profile change requests, partner extras, maintenance.
Written during development; NOT executed yet."""

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.common.utilities import utcnow
from app.core.config import Settings
from app.modules.admin import maintenance
from app.modules.auth.constants import StaffRole
from app.modules.notifications.models import Notification
from app.modules.partner_documents.models import PartnerDocumentVersion
from tests import factories
from tests.fakes import InMemoryStorage, RecordingEmail
from tests.helpers import (
    complete_partner,
    make_staff,
    onboard_partner,
    staff_headers,
    submitted_application,
)

ADM = "/api/v1/admin"


def sa_headers(client: TestClient, db: Session, settings: Settings) -> dict[str, str]:
    return staff_headers(client, make_staff(db, settings, StaffRole.SUPER_ADMINISTRATOR))


def test_settings_validation_and_permissions(
    client: TestClient, db: Session, settings: Settings
) -> None:
    sa = sa_headers(client, db, settings)
    bdm = staff_headers(client, make_staff(db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER))
    assert client.get(f"{ADM}/settings", headers=bdm).status_code == 403
    assert (
        client.put(
            f"{ADM}/settings/retention.partner_document_days", headers=sa, json={"value": "365"}
        ).status_code
        == 200
    )
    assert (
        client.put(
            f"{ADM}/settings/retention.partner_document_days", headers=sa, json={"value": "0"}
        ).status_code
        == 422
    )
    assert (
        client.put(
            f"{ADM}/settings/retention.partner_document_days", headers=sa, json={"value": "abc"}
        ).status_code
        == 422
    )
    assert (
        client.put(f"{ADM}/settings/made.up.key", headers=sa, json={"value": "1"}).status_code
        == 422
    )
    listed = client.get(f"{ADM}/settings", headers=sa).json()["data"]
    assert listed["values"] == {"retention.partner_document_days": "365"}
    assert (
        client.delete(f"{ADM}/settings/retention.partner_document_days", headers=sa).status_code
        == 200
    )


def test_template_override_is_used_and_validated(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    sa = sa_headers(client, db, settings)
    placeholders = client.get(f"{ADM}/notification-templates/placeholders", headers=sa)
    assert placeholders.status_code == 200
    assert {row["name"] for row in placeholders.json()["data"]} == {
        "name",
        "reference",
        "status_label",
        "link",
        "enquiry_type",
        "company",
        "category",
        "expires_on",
        "meeting_time",
    }
    bdm = staff_headers(client, make_staff(db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER))
    assert client.get(f"{ADM}/notification-templates/placeholders", headers=bdm).status_code == 403
    url = f"{ADM}/notification-templates/ack_general"
    assert (
        client.put(url, headers=sa, json={"subject": "Hi\nBcc: x", "text_body": "t"}).status_code
        == 422
    )
    assert (
        client.put(url, headers=sa, json={"subject": "s", "text_body": "$secret_value"}).status_code
        == 422
    )
    assert (
        client.put(
            f"{ADM}/notification-templates/password_reset",
            headers=sa,
            json={"subject": "s", "text_body": "no link here"},
        ).status_code
        == 422
    )
    assert (
        client.put(
            f"{ADM}/notification-templates/not_a_template",
            headers=sa,
            json={"subject": "s", "text_body": "t"},
        ).status_code
        == 404
    )
    ok = client.put(
        url,
        headers=sa,
        json={"subject": "Thanks $name ($reference)", "text_body": "Hello $name, ref $reference."},
    )
    assert ok.status_code == 200 and ok.json()["data"]["version"] == 1
    assert (
        client.put(
            url, headers=sa, json={"subject": "Thanks $name", "text_body": "v2 $name"}
        ).json()["data"]["version"]
        == 2
    )
    client.post("/api/v1/enquiries/contact", json=factories.contact(full_name="<b>Eve</b>"))
    ack = next(m for m in email.sent if m.to == "asha.rao@example.com" or "Eve" in m.text)
    assert (
        ack.text.startswith("v2 <b>Eve</b>")
        and "&lt;b&gt;Eve" in ack.html
        and "<b>Eve</b>" not in ack.html
    )
    prev = client.post(
        f"{url}/preview", headers=sa, json={"subject": "S $reference", "text_body": "B $name"}
    )
    assert prev.json()["data"]["subject"] == "S CS-ENQ-2026-000000"
    assert client.delete(url, headers=sa).status_code == 200
    email.sent.clear()
    client.post("/api/v1/enquiries/contact", json=factories.contact())
    assert "not an offer" in email.sent[0].text  # built-in restored


def test_mfa_reset_by_super_admin(client: TestClient, db: Session, settings: Settings) -> None:
    sa_user = make_staff(db, settings, StaffRole.SUPER_ADMINISTRATOR)
    sa = staff_headers(client, sa_user)
    other = make_staff(db, settings, StaffRole.PARTNER_REVIEWER)
    other_h = staff_headers(client, other)
    assert (
        client.post(f"{ADM}/users/{sa_user.id}/mfa-reset", headers=sa).status_code == 409
    )  # not your own
    assert client.post(f"{ADM}/users/{other.id}/mfa-reset", headers=other_h).status_code == 403
    assert client.post(f"{ADM}/users/{other.id}/mfa-reset", headers=sa).status_code == 200
    assert client.get("/api/v1/auth/me", headers=other_h).status_code == 401  # sessions revoked


def test_kpis(client: TestClient, db: Session, settings: Settings, email: RecordingEmail) -> None:
    sa = sa_headers(client, db, settings)
    client.post("/api/v1/enquiries/contact", json=factories.contact(lead_source="campaign-a"))
    onboard = onboard_partner(client, db, settings, email)
    submitted_application(client, onboard)
    data = client.get(f"{ADM}/reports/kpis", headers=sa).json()["data"]
    assert {"type": "general", "source": "campaign-a", "count": 1} in data[
        "enquiries_by_type_and_source"
    ]
    assert data["partner_application_completion"]["submitted"] == 1
    assert data["portal_adoption"]["active_partner_users"] == 1
    bdm = staff_headers(client, make_staff(db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER))
    bdm_kpis = client.get(f"{ADM}/reports/kpis", headers=bdm).json()["data"]
    assert bdm_kpis.get("partner_application_completion") is None  # super administrators only


def test_typed_aggregate_reports_and_role_scopes(
    client: TestClient, db: Session, settings: Settings
) -> None:
    sa = sa_headers(client, db, settings)
    bdm = staff_headers(client, make_staff(db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER))
    followups = client.get(f"{ADM}/reports/follow-ups", headers=bdm).json()["data"]
    assert set(followups) == {"total", "by_kind", "by_status", "by_month"}
    documents = client.get(f"{ADM}/reports/document-review", headers=sa).json()["data"]
    assert set(documents) == {"total_versions", "by_review_status", "avg_turnaround_hours"}
    communications = client.get(f"{ADM}/reports/communications", headers=sa).json()["data"]
    assert set(communications) == {"total", "by_delivery_status", "by_template"}
    assert client.get(f"{ADM}/reports/document-review", headers=bdm).status_code == 403
    assert client.get(f"{ADM}/reports/communications", headers=bdm).status_code == 403


def test_profile_change_request_flow_and_partner_extras(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    p = onboard_partner(client, db, settings, email)
    complete_partner(client, p, docs=False)
    url = "/api/v1/partner/organization/change-requests"
    assert (
        client.post(url, headers=p.headers, json={"changes": {}, "reason": "x"}).status_code == 422
    )
    r = client.post(
        url,
        headers=p.headers,
        json={"changes": {"employee_count": 200}, "reason": "Hired more staff"},
    )
    assert r.status_code == 201 and r.json()["data"]["status"] == "pending"
    assert (
        client.get("/api/v1/partner/organization", headers=p.headers).json()["data"][
            "employee_count"
        ]
        == 120
    )  # not applied yet
    sa = sa_headers(client, db, settings)
    req_id = client.get(f"{ADM}/profile-change-requests", headers=sa).json()["data"][0]["id"]
    done = client.post(
        f"{ADM}/profile-change-requests/{req_id}/decide",
        headers=sa,
        json={"approve": True, "note": "Verified"},
    )
    assert done.json()["data"]["status"] == "approved"
    assert (
        client.post(
            f"{ADM}/profile-change-requests/{req_id}/decide", headers=sa, json={"approve": False}
        ).status_code
        == 409
    )
    assert (
        client.get("/api/v1/partner/organization", headers=p.headers).json()["data"][
            "employee_count"
        ]
        == 200
    )
    hist = client.get("/api/v1/partner/organization/history", headers=p.headers).json()["data"]
    assert (
        hist[0]["changes"]["employee_count"]["new"] == "200"
        or hist[0]["changes"]["employee_count"]["new"] == 200
    )
    assert client.get(url, headers=p.headers).json()["data"][0]["status"] == "approved"
    notes = client.get("/api/v1/partner/notifications", headers=p.headers).json()["data"]
    assert any(n["template"] == "profile_change_decision" for n in notes) and all(
        "link" not in n for n in notes
    )
    client.post("/api/v1/enquiries/contact", json=factories.contact(business_email=p.email))
    mine = client.get("/api/v1/partner/enquiries", headers=p.headers).json()["data"]
    assert len(mine) == 1 and mine[0]["enquiry_type"] == "general"


def test_reviewer_assignment_sends_notification(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    admin = make_staff(db, settings, StaffRole.SUPER_ADMINISTRATOR)
    reviewer = make_staff(db, settings, StaffRole.PARTNER_REVIEWER)
    p = onboard_partner(client, db, settings, email, admin=admin)
    app_id = submitted_application(client, p)
    r = client.post(
        f"/api/v1/reviewer/applications/{app_id}/assign",
        headers=staff_headers(client, admin),
        json={"reviewer_id": str(reviewer.id)},
    )
    assert r.status_code == 200
    assert any(m.to == reviewer.email and "assigned to you" in m.subject for m in email.sent)


def test_retention_purge_and_expiry_reminders(
    client: TestClient,
    db: Session,
    settings: Settings,
    email: RecordingEmail,
    storage: InMemoryStorage,
) -> None:
    sa = sa_headers(client, db, settings)
    assert (
        maintenance.send_expiry_reminders(db) == 0 and maintenance.purge_retained(db, storage) == 0
    )  # inert without settings
    p = onboard_partner(client, db, settings, email)
    soon = (utcnow() + timedelta(days=10)).date().isoformat()
    up = client.post(
        "/api/v1/partner/documents",
        headers=p.headers,
        data={"category": "registration_proof", "expires_on": soon},
        files={"file": ("r.pdf", factories.PDF, "application/pdf")},
    )
    doc_id = up.json()["data"]["id"]
    client.put(f"{ADM}/settings/expiry_reminder_days", headers=sa, json={"value": "30"})
    assert maintenance.send_expiry_reminders(db) == 1
    assert maintenance.send_expiry_reminders(db) == 1  # queued again but deduplicated
    reminders = (
        db.execute(select(Notification).where(Notification.template_key == "expiry_reminder"))
        .scalars()
        .all()
    )
    assert len(reminders) == 1
    client.put(f"{ADM}/settings/retention.partner_document_days", headers=sa, json={"value": "1"})
    assert (
        client.delete(f"/api/v1/partner/documents/{doc_id}", headers=p.headers).status_code == 200
    )
    version = db.execute(select(PartnerDocumentVersion)).scalar_one()
    assert version.retention_date is not None and storage.exists(version.storage_key)
    assert maintenance.purge_retained(db, storage) == 0  # retention not over yet
    db.execute(
        update(PartnerDocumentVersion).values(retention_date=utcnow() - timedelta(seconds=1))
    )
    db.commit()
    assert maintenance.purge_retained(db, storage) == 1
    assert not storage.exists(version.storage_key)
    db.refresh(version)
    assert version.purged_at is not None
