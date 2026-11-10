"""PRD s.28 acceptance-level requirements: claims register, SLA/routing/escalation, failure
visibility, launch gate, catalog safeguards, privacy deletion, MFA recovery."""

from datetime import timedelta

from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.common.utilities import utcnow
from app.core.config import Settings
from app.modules.admin import maintenance
from app.modules.auth import mfa
from app.modules.auth.constants import StaffRole, UserStatus
from app.modules.auth.models import User
from app.modules.enquiries.models import Contact, Enquiry
from app.modules.notifications.models import Notification
from app.modules.notifications.service import dispatch_notifications
from tests import factories
from tests.conftest import AppFactory
from tests.fakes import RecordingEmail
from tests.helpers import bearer, last_token, login, make_staff, staff_headers

ADM = "/api/v1/admin"
AC = "/api/v1/admin/content"
CL = "/api/v1/admin/content-claims"


def hdr(client: TestClient, db: Session, settings: Settings, role: StaffRole) -> dict[str, str]:
    return staff_headers(client, make_staff(db, settings, role))


def test_claims_gate_publication(client: TestClient, db: Session, settings: Settings) -> None:
    ca = hdr(client, db, settings, StaffRole.CONTENT_ADMINISTRATOR)
    sa = hdr(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    claim = client.post(
        CL,
        headers=ca,
        json={"claim_text": "Partner X is our delivery partner", "category": "partner_reference"},
    ).json()["data"]
    assert claim["evidence_status"] == "pending_verification"
    assert (
        client.patch(
            f"{CL}/{claim['id']}", headers=ca, json={"evidence_status": "verified"}
        ).status_code
        == 403
    )
    item = client.post(
        AC,
        headers=ca,
        json={
            "slug": "ecosystem",
            "content_type": "page",
            "title": "Ecosystem",
            "body": "Text",
            "claim_ids": [claim["id"]],
        },
    ).json()["data"]["id"]
    assert (
        client.post(
            AC,
            headers=ca,
            json={
                "slug": "bad",
                "content_type": "page",
                "title": "t",
                "body": "b",
                "claim_ids": ["00000000-0000-0000-0000-000000000000"],
            },
        ).status_code
        == 422
    )
    client.post(f"{AC}/{item}/submit", headers=ca)
    client.post(f"{AC}/{item}/approve", headers=sa, json={})
    blocked = client.post(f"{AC}/{item}/publish", headers=ca)
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "CLAIMS_NOT_VERIFIED"
    client.patch(f"{CL}/{claim['id']}", headers=sa, json={"evidence_status": "verified"})
    assert (
        client.post(f"{AC}/{item}/publish", headers=ca).status_code == 409
    )  # verified but no written permission
    client.patch(f"{CL}/{claim['id']}", headers=sa, json={"publication_permission": True})
    assert client.post(f"{AC}/{item}/publish", headers=ca).status_code == 200
    assert client.get("/api/v1/content/ecosystem").status_code == 200
    # withdrawing the claim pulls the page off the site
    client.patch(f"{CL}/{claim['id']}", headers=sa, json={"evidence_status": "prohibited"})
    assert client.get("/api/v1/content/ecosystem").status_code == 404
    assert client.get(f"{AC}/{item}", headers=ca).json()["data"]["status"] == "draft"
    assert client.get(f"{CL}?status=prohibited", headers=ca).json()["meta"]["total"] == 1


def test_routing_sla_backup_owner_and_ack_promise(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    sa = hdr(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    bdm = make_staff(db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
    backup = make_staff(db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
    reviewer = make_staff(db, settings, StaffRole.PARTNER_REVIEWER)

    def put(k: str, v: str) -> Response:
        r: Response = client.put(f"{ADM}/settings/{k}", headers=sa, json={"value": v})
        return r

    assert put("sla.general", "0").status_code == 422
    assert put("route.owner.general", str(reviewer.id)).status_code == 422  # wrong role
    assert (
        put("route.owner.strategic", str(bdm.id)).status_code == 422
    )  # confidential queue: SA only
    assert put("sla.general", "24").status_code == 200
    assert put("route.owner.general", str(bdm.id)).status_code == 200
    assert put("route.backup.general", str(backup.id)).status_code == 200
    client.post("/api/v1/enquiries/contact", json=factories.contact())
    e = db.execute(select(Enquiry)).scalar_one()
    assert e.assigned_user_id == bdm.id and e.response_due_at is not None
    assert not any("aim to respond" in m.text for m in email.sent)  # no promise until enabled
    put("ack_promise_enabled", "true")
    email.sent.clear()
    client.post("/api/v1/enquiries/contact", json=factories.contact())
    assert any(
        "aim to respond within 24 hours" in m.text
        for m in email.sent
        if m.to == "asha.rao@example.com"
    )
    db.execute(update(User).where(User.id == bdm.id).values(status=UserStatus.DEACTIVATED))
    db.commit()
    ref = client.post("/api/v1/enquiries/contact", json=factories.contact()).json()["data"][
        "reference_number"
    ]
    newest = db.execute(select(Enquiry).where(Enquiry.reference_number == ref)).scalar_one()
    assert newest.assigned_user_id == backup.id  # out-of-office cover


def test_escalation_and_first_response(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    sa = hdr(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    client.put(f"{ADM}/settings/sla.general", headers=sa, json={"value": "1"})
    client.put(
        f"{ADM}/settings/escalation.email.general", headers=sa, json={"value": "boss@example.com"}
    )
    for _ in range(2):
        client.post("/api/v1/enquiries/contact", json=factories.contact())
    rows = list(db.execute(select(Enquiry).order_by(Enquiry.created_at)).scalars())
    db.execute(update(Enquiry).values(response_due_at=utcnow() - timedelta(hours=1)))
    db.commit()
    assert client.get(f"{ADM}/enquiries?sla_breached=true", headers=sa).json()["meta"]["total"] == 2
    client.post(
        f"{ADM}/enquiries/{rows[0].id}/follow-ups", headers=sa, json={"note": "Called"}
    )  # first response
    assert client.get(f"{ADM}/overview", headers=sa).json()["data"]["sla_breached"] == 1
    assert maintenance.escalate_overdue(db, settings) == 1
    assert maintenance.escalate_overdue(db, settings) == 0  # once per enquiry
    queued = (
        db.execute(select(Notification).where(Notification.template_key == "sla_escalation"))
        .scalars()
        .all()
    )
    assert [n.recipient for n in queued] == ["boss@example.com"]


def test_notification_failure_visibility_and_retry(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    sa = hdr(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    bdm = hdr(client, db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
    email.fail = True
    assert (
        client.post("/api/v1/enquiries/contact", json=factories.contact()).status_code == 201
    )  # not lost
    failed = client.get(f"{ADM}/notifications", headers=sa).json()
    assert failed["meta"]["total"] == 2 and failed["data"][0]["last_error"]
    assert client.get(f"{ADM}/overview", headers=sa).json()["data"]["failed_notifications"] == 2
    assert client.get(f"{ADM}/notifications", headers=bdm).status_code == 403
    email.fail = False
    assert client.post(f"{ADM}/notifications/dispatch", headers=sa).json()["data"]["queued"] == 2
    # The endpoint hands the work to a background task. The test harness nests every session in one
    # outer transaction, so run the dispatcher directly to observe its effect.
    assert dispatch_notifications(client.app.state.sessionmaker, email, settings) >= 0  # type: ignore[attr-defined]
    assert client.get(f"{ADM}/notifications", headers=sa).json()["meta"]["total"] == 0
    assert (
        client.post(f"{ADM}/notifications/{failed['data'][0]['id']}/retry", headers=sa).status_code
        == 404
    )  # already sent


def test_launch_readiness_and_public_contact(
    client: TestClient, db: Session, settings: Settings
) -> None:
    sa = hdr(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    state = client.get(f"{ADM}/launch-readiness", headers=sa).json()["data"]
    assert state["ready"] is False and set(state["contact"].values()) == {"pending"}
    assert client.get("/api/v1/site/contact").json()["data"] == {}
    for k, v in (
        ("contact.phone", "12345"),
        ("contact.email", "not-an-email"),
        ("contact.domain", "bad domain"),
    ):
        assert client.put(f"{ADM}/settings/{k}", headers=sa, json={"value": v}).status_code == 422
    client.put(f"{ADM}/settings/contact.email", headers=sa, json={"value": "Hello@Example.com"})
    client.put(f"{ADM}/settings/contact.phone", headers=sa, json={"value": "+1 (415) 555-0123"})
    client.put(f"{ADM}/settings/contact.address.omitted", headers=sa, json={"value": "true"})
    pub = client.get("/api/v1/site/contact").json()["data"]
    assert pub == {
        "email": "hello@example.com",
        "phone": "+14155550123",
    }  # omitted/unconfirmed never exposed
    contact = client.get(f"{ADM}/launch-readiness", headers=sa).json()["data"]["contact"]
    assert (
        contact["email"] == "confirmed"
        and contact["address"] == "omitted"
        and contact["domain"] == "pending"
    )


def test_catalog_is_illustrative_and_criteria_proposed(client: TestClient) -> None:
    cats = client.get("/api/v1/catalog/project-categories").json()["data"]
    assert len(cats) == 13 and all(c["illustrative"] for c in cats)
    crit = client.get("/api/v1/catalog/partner-criteria").json()["data"]
    assert crit["status"] == "proposed" and len(crit["submission_checklist"]) == 8
    turnover = next(c for c in crit["criteria"] if c["key"] == "annual_turnover")
    assert turnover["applies_to"] == ["direct_project_engagement"]


def test_privacy_deletion_execution(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    sa = hdr(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    client.post(
        "/api/v1/enquiries/contact", json=factories.contact(business_email="forget.me@example.com")
    )
    client.post(
        "/api/v1/newsletter/subscribe", json={"email": "forget.me@example.com", "consent": True}
    )
    ref = client.post(
        "/api/v1/privacy/requests", json={"email": "forget.me@example.com", "kind": "deletion"}
    ).json()["data"]["reference"]
    req = next(
        r
        for r in client.get(f"{ADM}/privacy-requests", headers=sa).json()["data"]
        if r["reference"] == ref
    )
    assert (
        client.post(f"{ADM}/privacy-requests/{req['id']}/execute", headers=sa).status_code == 409
    )  # not in progress
    client.post(
        "/api/v1/privacy/requests/verify",
        json={"token": last_token(email, "forget.me@example.com")},
    )
    client.post(f"{ADM}/privacy-requests/{req['id']}", headers=sa, json={"status": "in_progress"})
    done = client.post(f"{ADM}/privacy-requests/{req['id']}/execute", headers=sa).json()["data"]
    assert done["contacts_anonymised"] == 1 and done["newsletter_rows_removed"] == 1
    contact = db.execute(select(Contact)).scalars().first()
    assert (
        contact is not None
        and contact.full_name == "Deleted contact"
        and "forget.me" not in contact.business_email
    )
    assert (
        client.post(f"{ADM}/privacy-requests/{req['id']}/execute", headers=sa).status_code == 409
    )  # only once
    assert "forget.me@example.com" not in client.get(f"{ADM}/privacy-requests", headers=sa).text


def test_mfa_recovery_codes_regeneration(app_factory: AppFactory, settings: Settings) -> None:
    app = app_factory(staff_mfa_required=True)
    with TestClient(app, raise_server_exceptions=False) as client:
        db: Session = app.state.sessionmaker()
        user = make_staff(db, settings, StaffRole.PARTNER_REVIEWER)
        h = bearer(login(client, user.email)["access_token"])
        secret = client.post("/api/v1/auth/mfa/enroll", headers=h).json()["data"]["secret"]
        old = client.post(
            "/api/v1/auth/mfa/confirm",
            headers=h,
            json={"code": mfa.code_at(secret, mfa.current_step())},
        ).json()["data"]["recovery_codes"]
        url = "/api/v1/auth/mfa/recovery-codes"
        assert client.post(url, headers=h, json={"code": "000000"}).status_code == 401
        new = client.post(
            url, headers=h, json={"code": mfa.code_at(secret, mfa.current_step() + 1)}
        ).json()["data"]["recovery_codes"]
        assert len(new) == 8 and not set(new) & set(old)
        h2 = bearer(login(client, user.email)["access_token"])
        assert (
            client.post(
                "/api/v1/auth/mfa/verify", headers=h2, json={"recovery_code": old[0]}
            ).status_code
            == 401
        )  # retired
        assert (
            client.post(
                "/api/v1/auth/mfa/verify", headers=h2, json={"recovery_code": new[0]}
            ).status_code
            == 200
        )
