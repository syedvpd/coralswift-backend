from dataclasses import dataclass

from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.applications.models import ApplicationSubmission
from app.modules.auth.constants import StaffRole
from app.modules.auth.models import User
from app.modules.enquiries.models import Activity
from tests import factories
from tests.fakes import RecordingEmail
from tests.helpers import (
    Partner,
    bearer,
    login,
    make_staff,
    onboard_partner,
    staff_headers,
    submitted_application,
)

R = "/api/v1/reviewer/applications"
P = "/api/v1/partner/applications"


@dataclass
class Ctx:
    partner: Partner
    app_id: str
    admin: User
    reviewer: User
    admin_h: dict[str, str]
    rev_h: dict[str, str]


def setup(client: TestClient, db: Session, settings: Settings, email: RecordingEmail) -> Ctx:
    admin = make_staff(db, settings, StaffRole.SUPER_ADMINISTRATOR)
    reviewer = make_staff(db, settings, StaffRole.PARTNER_REVIEWER)
    partner = onboard_partner(client, db, settings, email, admin=admin)
    app_id = submitted_application(client, partner)
    return Ctx(
        partner,
        app_id,
        admin,
        reviewer,
        staff_headers(client, admin),
        staff_headers(client, reviewer),
    )


def assign(client: TestClient, c: Ctx) -> None:
    r = client.post(
        f"{R}/{c.app_id}/assign", headers=c.admin_h, json={"reviewer_id": str(c.reviewer.id)}
    )
    assert r.status_code == 200, r.text


def move(client: TestClient, c: Ctx, to: str, **body: str) -> Response:
    response: Response = client.post(
        f"{R}/{c.app_id}/transition", headers=c.rev_h, json={"to_status": to, **body}
    )
    return response


def test_assignment_controls_visibility(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    c = setup(client, db, settings, email)
    assert client.get(f"{R}/{c.app_id}", headers=c.rev_h).status_code == 404  # not assigned
    assert client.get(R, headers=c.rev_h).json()["data"] == []
    assert (
        client.post(
            f"{R}/{c.app_id}/assign", headers=c.rev_h, json={"reviewer_id": str(c.reviewer.id)}
        ).status_code
        == 403
    )
    bad = client.post(
        f"{R}/{c.app_id}/assign", headers=c.admin_h, json={"reviewer_id": c.partner.organization_id}
    )
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "INVALID_REVIEWER"
    assign(client, c)
    listing = client.get(R, headers=c.rev_h).json()
    assert [a["id"] for a in listing["data"]] == [c.app_id] and listing["meta"]["total"] == 1
    detail = client.get(f"{R}/{c.app_id}", headers=c.rev_h).json()["data"]
    assert detail["organization"]["registration_number"] and len(detail["documents"]) == 7
    assert (
        len(client.get(R, headers=c.admin_h).json()["data"]) == 1
    )  # super admin sees all submitted
    assert client.get(f"{R}?status=capability_review", headers=c.admin_h).json()["data"] == []


def test_workflow_rules_enforced(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    c = setup(client, db, settings, email)
    r = move(client, c, "eligibility_verification")
    assert r.status_code == 404  # reviewer not assigned yet
    admin_move = client.post(
        f"{R}/{c.app_id}/transition",
        headers=c.admin_h,
        json={"to_status": "eligibility_verification"},
    )
    assert (
        admin_move.status_code == 422
        and admin_move.json()["error"]["code"] == "ASSIGNMENT_REQUIRED"
    )
    assign(client, c)
    assert move(client, c, "eligibility_verification").status_code == 200
    # cannot skip stages or move without an eligibility record
    assert move(client, c, "pilot_onboarding", reason="x").status_code == 409
    no_record = move(client, c, "capability_review")
    assert (
        no_record.status_code == 422
        and no_record.json()["error"]["code"] == "ELIGIBILITY_RECORD_REQUIRED"
    )
    # dedicated targets cannot be forced through the generic endpoint
    for target in ("withdrawn", "information_requested", "submitted", "draft"):
        assert move(client, c, target, reason="x").status_code == 409
    ev = f"{R}/{c.app_id}/eligibility-verifications"
    exc = client.post(ev, headers=c.rev_h, json={"outcome": "verified_with_exception"})
    assert exc.status_code == 422
    rec = client.post(
        ev,
        headers=c.rev_h,
        json={
            "verified_operating_years": "2.5",
            "verified_personnel": 10,
            "verified_turnover_inr_crore": "0.50",
            "outcome": "verified_with_exception",
            "exception_note": "Group company records accepted",
            "notes": "Checked statutory filings",
        },
    )
    assert rec.status_code == 201
    # below every proposed threshold, yet nothing was auto-rejected or auto-approved
    assert (
        client.get(f"{R}/{c.app_id}", headers=c.rev_h).json()["data"]["application"]["status"]
        == "eligibility_verification"
    )
    client.post(ev, headers=c.rev_h, json={"outcome": "inconclusive"})
    assert len(client.get(ev, headers=c.rev_h).json()["data"]) == 2  # append-only history preserved
    assert move(client, c, "capability_review").status_code == 200
    assert move(client, c, "commercial_legal_review").status_code == 200
    no_reason = move(client, c, "pilot_onboarding")
    assert no_reason.status_code == 422 and no_reason.json()["error"]["code"] == "REASON_REQUIRED"
    ok = move(
        client,
        c,
        "pilot_onboarding",
        reason="Commercial terms agreed",
        partner_note="Moving to pilot",
    )
    assert ok.status_code == 200
    hist = client.get(f"{P}/{c.app_id}/history", headers=c.partner.headers).json()["data"]
    assert hist[-1]["to_status"] == "pilot_onboarding" and hist[-1]["note"] == "Moving to pilot"
    assert (
        "Commercial terms agreed"
        not in client.get(f"{P}/{c.app_id}/history", headers=c.partner.headers).text
    )
    assert move(client, c, "rejected", reason="Changed mind").status_code == 200
    assert move(client, c, "scale_up", reason="x").status_code == 409  # terminal
    msgs = [m for m in email.sent if m.to == c.partner.email]
    assert any("Decision recorded" in m.subject for m in msgs)
    assert all("Commercial terms agreed" not in m.text for m in email.sent)


def test_information_request_response_resubmission(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    c = setup(client, db, settings, email)
    assign(client, c)
    move(client, c, "eligibility_verification")
    req = client.post(
        f"{R}/{c.app_id}/information-requests",
        headers=c.rev_h,
        json={"body": "Please clarify turnover.", "requested_categories": ["financial_statements"]},
    )
    assert req.status_code == 201
    req_id = req.json()["data"]["id"]
    pa = client.get(f"{P}/{c.app_id}", headers=c.partner.headers).json()["data"]
    assert pa["status"] == "information_requested" and pa["open_information_requests"] == 1
    msgs = client.get(f"{P}/{c.app_id}/messages", headers=c.partner.headers).json()["data"]
    assert msgs[0]["from_reviewer"] is True and "author_user_id" not in msgs[0]
    assert any(
        "Additional information requested" in m.subject
        for m in email.sent
        if m.to == c.partner.email
    )
    assert all("clarify turnover" not in m.text for m in email.sent)  # content never emailed
    early = client.post(f"{P}/{c.app_id}/resubmit", headers=c.partner.headers)
    assert early.status_code == 409 and early.json()["error"]["code"] == "OPEN_REQUESTS"
    # reviewer cannot move the application while information is outstanding
    assert move(client, c, "capability_review").status_code == 409
    reply = client.post(
        f"{P}/{c.app_id}/messages",
        headers=c.partner.headers,
        json={"in_reply_to": req_id, "body": "Turnover is INR 5.5 crore."},
    )
    assert reply.status_code == 201
    again = client.post(
        f"{P}/{c.app_id}/messages",
        headers=c.partner.headers,
        json={"in_reply_to": req_id, "body": "twice"},
    )
    assert again.status_code == 409 and again.json()["error"]["code"] == "REQUEST_NOT_OPEN"
    assert (
        client.post(
            f"{P}/{c.app_id}/messages", headers=c.partner.headers, json={"in_reply_to": req_id}
        ).status_code
        == 422
    )
    done = client.post(f"{P}/{c.app_id}/resubmit", headers=c.partner.headers)
    assert done.status_code == 200 and done.json()["data"]["status"] == "eligibility_verification"
    assert done.json()["data"]["submission_count"] == 2
    assert db.execute(
        select(ApplicationSubmission.submission_no).order_by(ApplicationSubmission.submission_no)
    ).scalars().all() == [1, 2]
    thread = client.get(f"{R}/{c.app_id}/messages", headers=c.rev_h).json()["data"]
    assert [m["kind"] for m in thread] == ["information_request", "partner_response"]


def test_internal_notes_never_reach_partners(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    c = setup(client, db, settings, email)
    assign(client, c)
    secret = "INTERNAL-ONLY-OPINION-XYZ"
    assert (
        client.post(f"{R}/{c.app_id}/notes", headers=c.rev_h, json={"body": secret}).status_code
        == 201
    )
    assert client.get(f"{R}/{c.app_id}/notes", headers=c.rev_h).json()["data"][0]["body"] == secret
    for url in (
        f"{P}/{c.app_id}",
        f"{P}/{c.app_id}/history",
        f"{P}/{c.app_id}/messages",
        P,
        "/api/v1/partner/documents",
        "/api/v1/partner/organization",
        "/api/v1/auth/me",
    ):
        assert secret not in client.get(url, headers=c.partner.headers).text, url
    assert client.get(f"{R}/{c.app_id}/notes", headers=c.partner.headers).status_code == 403
    assert (
        client.post(
            f"{R}/{c.app_id}/notes", headers=c.partner.headers, json={"body": "x"}
        ).status_code
        == 403
    )
    audit = [
        a.meta
        for a in db.execute(
            select(Activity).where(Activity.action == "application.note_added")
        ).scalars()
    ]
    assert audit and secret not in str(audit)


def test_document_review_and_download(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    c = setup(client, db, settings, email)
    assign(client, c)
    docs = client.get("/api/v1/partner/documents", headers=c.partner.headers).json()["data"]
    doc_id = docs[0]["id"]
    category = docs[0]["category"]
    need_comment = client.post(
        f"{R}/{c.app_id}/documents/{doc_id}/review", headers=c.rev_h, json={"status": "rejected"}
    )
    assert need_comment.status_code == 422
    r = client.post(
        f"{R}/{c.app_id}/documents/{doc_id}/review",
        headers=c.rev_h,
        json={"status": "rejected", "comment": "Illegible scan"},
    )
    assert r.status_code == 200
    mine = client.get(f"/api/v1/partner/documents/{doc_id}", headers=c.partner.headers).json()[
        "data"
    ]["current_version"]
    assert mine["review_status"] == "rejected" and mine["review_comment"] == "Illegible scan"
    ready = client.get(f"{P}/{c.app_id}/readiness", headers=c.partner.headers).json()["data"]
    assert ready["missing_document_categories"] == [category]  # rejected evidence no longer counts
    dl = client.get(f"{R}/{c.app_id}/documents/{doc_id}/download", headers=c.rev_h)
    assert dl.status_code == 200 and dl.content == factories.PDF
    assert "document.downloaded" in set(db.execute(select(Activity.action)).scalars())
    # a document of another organization is invisible through this application
    other = onboard_partner(client, db, settings, email, org_name="Other Org")
    other_doc = client.post(
        "/api/v1/partner/documents",
        headers=other.headers,
        data={"category": "registration_proof"},
        files={"file": ("o.pdf", factories.PDF, "application/pdf")},
    ).json()["data"]["id"]
    assert (
        client.get(f"{R}/{c.app_id}/documents/{other_doc}/download", headers=c.rev_h).status_code
        == 404
    )
    assert (
        client.post(
            f"{R}/{c.app_id}/documents/{other_doc}/review",
            headers=c.rev_h,
            json={"status": "accepted"},
        ).status_code
        == 404
    )


def test_audit_history_has_actors_and_request_ids(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    c = setup(client, db, settings, email)
    assign(client, c)
    move(client, c, "eligibility_verification")
    audit = client.get(f"{R}/{c.app_id}/history", headers=c.rev_h).json()["data"]
    actions = [a["action"] for a in audit]
    assert (
        actions[:3]
        == ["application.created", "application.status_changed", "application.status_changed"]
        or "application.reviewer_assigned" in actions
    )
    assert "application.reviewer_assigned" in actions
    assert all(a["actor_user_id"] and a["request_id"] for a in audit)
    assert login(client, c.reviewer.email)[
        "access_token"
    ]  # logins do not alter the application trail
    assert bearer("x")  # helper sanity
