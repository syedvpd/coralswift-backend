import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.auth.constants import StaffRole
from app.modules.enquiries.models import Activity
from app.modules.notifications.models import Notification
from tests.fakes import RecordingEmail
from tests.helpers import (
    PASSWORD,
    Partner,
    bearer,
    complete_partner,
    create_draft,
    last_token,
    login,
    make_staff,
    staff_headers,
)

R = "/api/v1/reviewer/applications"
P = "/api/v1/partner/applications"


def test_audit_table_is_append_only(client: TestClient, db: Session, settings: Settings) -> None:
    make_staff(db, settings, StaffRole.PARTNER_REVIEWER)  # creates an audit row
    assert db.execute(select(Activity)).scalars().first() is not None
    with pytest.raises(DBAPIError, match="append-only"), db.begin_nested():
        db.execute(update(Activity).values(action="tampered"))
    with pytest.raises(DBAPIError, match="append-only"), db.begin_nested():
        db.execute(delete(Activity))


def test_full_partner_journey(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    # 1. access is granted through the invitation process
    admin = make_staff(db, settings, StaffRole.SUPER_ADMINISTRATOR)
    reviewer = make_staff(db, settings, StaffRole.PARTNER_REVIEWER)
    ah, rh = staff_headers(client, admin), staff_headers(client, reviewer)
    r = client.post(
        "/api/v1/reviewer/invitations",
        headers=ah,
        json={
            "email": "journey@example.com",
            "full_name": "Asha Rao",
            "new_organization_legal_name": "Journey Ltd",
        },
    )
    assert r.status_code == 201
    token = last_token(email, "journey@example.com")
    assert (
        client.post(
            "/api/v1/auth/invitations/accept", json={"token": token, "password": PASSWORD}
        ).status_code
        == 200
    )
    # 2. partner logs in
    tokens = login(client, "journey@example.com")
    ph = bearer(tokens["access_token"])
    # 3. completes the company profile, 4. uploads the required documents
    partner = Partner("journey@example.com", r.json()["data"]["organization_id"], ph, tokens)
    complete_partner(client, partner)
    # 5. creates and 6. submits the application
    app_id = create_draft(client, partner)
    assert client.post(f"{P}/{app_id}/submit", headers=ph).json()["data"]["status"] == "submitted"
    # 7. an authorised reviewer gets it (assignment by super administrator)
    assert client.get(f"{R}/{app_id}", headers=rh).status_code == 404
    client.post(f"{R}/{app_id}/assign", headers=ah, json={"reviewer_id": str(reviewer.id)})
    detail = client.get(f"{R}/{app_id}", headers=rh).json()["data"]
    assert detail["application"]["organization_name"] == "Journey Ltd"
    # 8. reviews company evidence
    doc = detail["documents"][0]["id"]
    assert client.get(f"{R}/{app_id}/documents/{doc}/download", headers=rh).status_code == 200
    assert (
        client.post(
            f"{R}/{app_id}/documents/{doc}/review", headers=rh, json={"status": "accepted"}
        ).status_code
        == 200
    )
    client.post(
        f"{R}/{app_id}/transition",
        headers=rh,
        json={
            "to_status": "eligibility_verification",
            "partner_note": "Eligibility review started",
        },
    )
    # 9. requests additional information
    req = client.post(
        f"{R}/{app_id}/information-requests",
        headers=rh,
        json={"body": "Please confirm headcount evidence."},
    ).json()["data"]["id"]
    # 10. partner responds and resubmits
    assert (
        client.post(
            f"{P}/{app_id}/messages",
            headers=ph,
            json={"in_reply_to": req, "body": "Payroll summary uploaded."},
        ).status_code
        == 201
    )
    assert (
        client.post(f"{P}/{app_id}/resubmit", headers=ph).json()["data"]["status"]
        == "eligibility_verification"
    )
    # 11. reviewer records eligibility verification
    ev = client.post(
        f"{R}/{app_id}/eligibility-verifications",
        headers=rh,
        json={
            "verified_operating_years": "9",
            "verified_personnel": 120,
            "verified_turnover_inr_crore": "5.5",
            "outcome": "verified",
            "notes": "Payroll and audited accounts checked",
        },
    )
    assert ev.status_code == 201
    # 12. reviewer advances the permitted stage
    assert (
        client.post(
            f"{R}/{app_id}/transition",
            headers=rh,
            json={"to_status": "capability_review", "partner_note": "Moving to capability review"},
        ).status_code
        == 200
    )
    # 13. partner sees the permitted status update only
    mine = client.get(f"{P}/{app_id}", headers=ph).json()["data"]
    assert mine["status"] == "capability_review" and mine["status_label"] == "Capability review"
    hist = client.get(f"{P}/{app_id}/history", headers=ph).json()["data"]
    assert [h["to_status"] for h in hist] == [
        "draft",
        "submitted",
        "eligibility_verification",
        "information_requested",
        "eligibility_verification",
        "capability_review",
    ]
    assert (
        "Payroll and audited accounts checked" not in client.get(f"{P}/{app_id}", headers=ph).text
    )
    # 14. the audit trail records the whole workflow
    audit = client.get(f"{R}/{app_id}/history", headers=rh).json()["data"]
    actions = [a["action"] for a in audit]
    for expected in (
        "application.created",
        "application.status_changed",
        "application.reviewer_assigned",
        "application.information_requested",
        "application.partner_responded",
        "application.eligibility_verified",
    ):
        assert expected in actions, expected
    assert all(a["request_id"] for a in audit)
    everything = " ".join(str(a["meta"]) for a in audit)
    assert "Payroll" not in everything and PASSWORD not in everything and "cs_" not in everything
    # org-level audit rows carry actor and organisation
    org_events = (
        db.execute(select(Activity).where(Activity.action == "organization.profile_updated"))
        .scalars()
        .all()
    )
    assert org_events and all(e.organization_id and e.actor_user_id for e in org_events)
    # notifications went through the outbox: console-style emails, no secrets left in rows
    outbox = db.execute(select(Notification)).scalars().all()
    assert outbox and all("link" not in n.context for n in outbox)
    assert any("Additional information requested" in m.subject for m in email.sent)
