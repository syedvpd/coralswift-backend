import re
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.auth.constants import StaffRole, UserStatus
from app.modules.auth.models import User
from app.modules.organizations.constants import MembershipStatus
from app.modules.organizations.models import PartnerMembership
from tests import factories
from tests.fakes import RecordingEmail
from tests.helpers import (
    complete_partner,
    make_staff,
    onboard_partner,
    staff_headers,
    submitted_application,
)

P = "/api/v1/partner/applications"
R = "/api/v1/reviewer/applications"
D = "/api/v1/partner/documents"


def test_every_protected_route_rejects_anonymous_requests(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()["paths"]
    checked = 0
    for path, ops in spec.items():
        if not path.startswith(
            (
                "/api/v1/partner",
                "/api/v1/reviewer",
                "/api/v1/auth/me",
                "/api/v1/auth/sessions",
                "/api/v1/auth/logout",
                "/api/v1/auth/mfa",
            )
        ):
            continue
        url = re.sub(r"\{[^}]+\}", str(uuid.uuid4()), path)
        for method in ops:
            r = client.request(method, url)
            assert r.status_code == 401, (method, path, r.status_code)
            checked += 1
    assert checked >= 35


def test_role_separation(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    partner = onboard_partner(client, db, settings, email)
    reviewer = make_staff(db, settings, StaffRole.PARTNER_REVIEWER)
    rh = staff_headers(client, reviewer)
    # partner token on staff routes
    assert client.get(R, headers=partner.headers).status_code == 403
    assert (
        client.post(
            "/api/v1/reviewer/invitations",
            headers=partner.headers,
            json={"email": "x@example.com", "full_name": "X", "new_organization_legal_name": "X"},
        ).status_code
        == 403
    )
    # staff token on partner routes
    for url in (P, D, "/api/v1/partner/organization"):
        assert client.get(url, headers=rh).status_code == 403, url
    # reviewer is not a super administrator
    assert (
        client.post(
            "/api/v1/reviewer/invitations",
            headers=rh,
            json={"email": "x@example.com", "full_name": "X", "new_organization_legal_name": "X"},
        ).status_code
        == 403
    )


def test_cross_organization_idor_matrix(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    admin = make_staff(db, settings, StaffRole.SUPER_ADMINISTRATOR)
    reviewer = make_staff(db, settings, StaffRole.PARTNER_REVIEWER)
    a = onboard_partner(client, db, settings, email, org_name="Org A", admin=admin)
    b = onboard_partner(client, db, settings, email, org_name="Org B", admin=admin)
    b_app = submitted_application(client, b)
    ah, rh = staff_headers(client, admin), staff_headers(client, reviewer)
    client.post(f"{R}/{b_app}/assign", headers=ah, json={"reviewer_id": str(reviewer.id)})
    req = client.post(
        f"{R}/{b_app}/information-requests", headers=rh, json={"body": "Need more."}
    ).json()["data"]["id"]
    b_doc = client.get(D, headers=b.headers).json()["data"][0]["id"]

    attempts = [
        ("get", f"{P}/{b_app}", None),
        ("patch", f"{P}/{b_app}", {"cover_note": "pwned"}),
        ("post", f"{P}/{b_app}/submit", None),
        ("post", f"{P}/{b_app}/resubmit", None),
        ("post", f"{P}/{b_app}/withdraw", {}),
        ("get", f"{P}/{b_app}/history", None),
        ("get", f"{P}/{b_app}/messages", None),
        ("get", f"{P}/{b_app}/readiness", None),
        ("post", f"{P}/{b_app}/messages", {"in_reply_to": req, "body": "I am an intruder"}),
        ("get", f"{D}/{b_doc}", None),
        ("get", f"{D}/{b_doc}/download", None),
        ("get", f"{D}/{b_doc}/history", None),
        ("delete", f"{D}/{b_doc}", None),
    ]
    for method, url, body in attempts:
        kwargs = {"json": body} if body is not None else {}
        r = client.request(method, url, headers=a.headers, **kwargs)
        assert r.status_code == 404, (method, url, r.status_code, r.text)
    r = client.post(
        f"{D}/{b_doc}/versions",
        headers=a.headers,
        files={"file": ("n.pdf", factories.PDF, "application/pdf")},
    )
    assert r.status_code == 404
    assert client.get(P, headers=a.headers).json()["data"] == []
    # B's data is untouched
    got = client.get(f"{P}/{b_app}", headers=b.headers).json()["data"]
    assert got["cover_note"] is None and got["status"] == "information_requested"
    assert (
        client.get(f"{P}/{b_app}/messages", headers=b.headers).json()["data"][0]["status"] == "open"
    )


def test_reviewer_cannot_act_outside_assignment(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    admin = make_staff(db, settings, StaffRole.SUPER_ADMINISTRATOR)
    r1 = make_staff(db, settings, StaffRole.PARTNER_REVIEWER)
    r2 = make_staff(db, settings, StaffRole.PARTNER_REVIEWER)
    p = onboard_partner(client, db, settings, email, admin=admin)
    app_id = submitted_application(client, p)
    client.post(
        f"{R}/{app_id}/assign",
        headers=staff_headers(client, admin),
        json={"reviewer_id": str(r1.id)},
    )
    h2 = staff_headers(client, r2)
    doc_id = client.get(D, headers=p.headers).json()["data"][0]["id"]
    for method, url, body in [
        ("get", f"{R}/{app_id}", None),
        ("post", f"{R}/{app_id}/transition", {"to_status": "eligibility_verification"}),
        ("post", f"{R}/{app_id}/information-requests", {"body": "x"}),
        ("post", f"{R}/{app_id}/notes", {"body": "x"}),
        ("get", f"{R}/{app_id}/notes", None),
        ("post", f"{R}/{app_id}/eligibility-verifications", {"outcome": "verified"}),
        ("get", f"{R}/{app_id}/documents/{doc_id}/download", None),
        ("post", f"{R}/{app_id}/documents/{doc_id}/review", {"status": "accepted"}),
        ("get", f"{R}/{app_id}/history", None),
        ("get", f"{R}/{app_id}/messages", None),
    ]:
        kwargs = {"json": body} if body is not None else {}
        assert client.request(method, url, headers=h2, **kwargs).status_code == 404, (method, url)
    assert (
        client.post(
            f"{R}/{app_id}/assign", headers=h2, json={"reviewer_id": str(r2.id)}
        ).status_code
        == 403
    )


def test_deactivated_users_and_memberships_lose_access(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    reviewer = make_staff(db, settings, StaffRole.PARTNER_REVIEWER)
    rh = staff_headers(client, reviewer)
    assert client.get(R, headers=rh).status_code == 200
    db.execute(update(User).where(User.id == reviewer.id).values(status=UserStatus.DEACTIVATED))
    db.commit()
    assert client.get(R, headers=rh).status_code == 401
    partner = onboard_partner(client, db, settings, email)
    assert client.get("/api/v1/partner/organization", headers=partner.headers).status_code == 200
    db.execute(update(PartnerMembership).values(status=MembershipStatus.REMOVED))
    db.commit()
    assert client.get("/api/v1/partner/organization", headers=partner.headers).status_code == 403


def test_partner_responses_never_expose_reviewer_only_fields(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    admin = make_staff(db, settings, StaffRole.SUPER_ADMINISTRATOR)
    reviewer = make_staff(db, settings, StaffRole.PARTNER_REVIEWER)
    p = onboard_partner(client, db, settings, email, admin=admin)
    app_id = submitted_application(client, p)
    rh = staff_headers(client, reviewer)
    client.post(
        f"{R}/{app_id}/assign",
        headers=staff_headers(client, admin),
        json={"reviewer_id": str(reviewer.id)},
    )
    client.post(
        f"{R}/{app_id}/transition",
        headers=rh,
        json={
            "to_status": "eligibility_verification",
            "reason": "TOP-SECRET-REASON",
            "partner_note": "Review started",
        },
    )
    client.post(f"{R}/{app_id}/information-requests", headers=rh, json={"body": "Please clarify."})
    for url in (
        P,
        f"{P}/{app_id}",
        f"{P}/{app_id}/history",
        f"{P}/{app_id}/messages",
        f"{P}/{app_id}/readiness",
    ):
        text = client.get(url, headers=p.headers).text
        for forbidden in (
            "TOP-SECRET-REASON",
            "assigned_reviewer_id",
            str(reviewer.id),
            '"reason"',
            "author_user_id",
            "storage_key",
        ):
            assert forbidden not in text, (url, forbidden)


def test_password_never_in_any_response(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    p = onboard_partner(client, db, settings, email)
    complete_partner(client, p, docs=False)
    for url in ("/api/v1/auth/me", "/api/v1/auth/sessions", "/api/v1/partner/organization"):
        text = client.get(url, headers=p.headers).text
        assert (
            "password" not in text.lower()
            and "argon2" not in text
            and p.tokens["refresh_token"] not in text
        )
