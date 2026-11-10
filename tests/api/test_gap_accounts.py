"""Gap closure: assignee picker, account administration, invitation lifecycle, suspension."""

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.common.utilities import utcnow
from app.core.config import Settings
from app.modules.auth.constants import StaffRole
from app.modules.auth.models import AuthToken
from tests.conftest import AppFactory
from tests.fakes import RecordingEmail
from tests.helpers import PASSWORD, bearer, last_token, login, make_staff, onboard_partner

ADM = "/api/v1/admin"
A = "/api/v1/auth"
STRONG = "a-new-strong-passphrase-7"


def _hdr(client: TestClient, db: Session, settings: Settings, role: StaffRole) -> dict[str, str]:
    return bearer(login(client, make_staff(db, settings, role).email)["access_token"])


def test_assignee_picker_is_open_to_staff_and_exposes_names_only(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    sa = _hdr(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    bdm = _hdr(client, db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
    rev = _hdr(client, db, settings, StaffRole.PARTNER_REVIEWER)
    cms = _hdr(client, db, settings, StaffRole.CONTENT_ADMINISTRATOR)
    enq = client.get(f"{ADM}/assignees?purpose=enquiries", headers=bdm).json()["data"]
    assert {r["staff_role"] for r in enq} == {"super_administrator", "business_development_manager"}
    assert all(set(r) == {"id", "full_name", "staff_role"} for r in enq)  # no email, no status
    apps = client.get(f"{ADM}/assignees?purpose=applications", headers=rev).json()["data"]
    assert {r["staff_role"] for r in apps} == {"super_administrator", "partner_reviewer"}
    assert client.get(f"{ADM}/assignees", headers=cms).status_code == 200  # any staff role
    assert client.get(f"{ADM}/assignees", headers=sa).status_code == 200
    assert client.get(f"{ADM}/assignees").status_code == 401
    partner = onboard_partner(client, db, settings, email)
    assert client.get(f"{ADM}/assignees", headers=partner.headers).status_code == 403
    assert client.get(f"{ADM}/assignees?purpose=bogus", headers=sa).status_code == 422


def test_accounts_are_super_admin_only_filterable_and_sortable(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    sa = _hdr(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    for role in (StaffRole.BUSINESS_DEVELOPMENT_MANAGER, StaffRole.PARTNER_REVIEWER):
        assert (
            client.get(f"{ADM}/accounts", headers=_hdr(client, db, settings, role)).status_code
            == 403
        )
    onboard_partner(client, db, settings, email, org_name="Acme Dispatch Ltd")
    body = client.get(f"{ADM}/accounts?page_size=100", headers=sa).json()
    assert body["meta"]["total"] == len(body["data"]) >= 3
    partners = client.get(f"{ADM}/accounts?user_type=partner", headers=sa).json()["data"]
    assert partners and all(a["user_type"] == "partner" for a in partners)
    assert partners[0]["organization"]["legal_name"] == "Acme Dispatch Ltd"
    staff = client.get(f"{ADM}/accounts?user_type=staff&role=super_administrator", headers=sa)
    assert all(a["staff_role"] == "super_administrator" for a in staff.json()["data"])
    q = client.get(f"{ADM}/accounts", params={"q": partners[0]["email"][:12]}, headers=sa)
    assert partners[0]["id"] in [a["id"] for a in q.json()["data"]]
    asc = client.get(f"{ADM}/accounts?sort=email&page_size=100", headers=sa).json()["data"]
    assert [a["email"] for a in asc] == sorted(a["email"] for a in asc)
    assert client.get(f"{ADM}/accounts?sort=password", headers=sa).status_code == 422
    one = client.get(f"{ADM}/accounts/{partners[0]['id']}", headers=sa).json()["data"]
    assert one["recent_activity"] and "password" not in str(one).lower().replace(
        "password_reset", ""
    )
    unknown = client.get(f"{ADM}/accounts/00000000-0000-0000-0000-000000000000", headers=sa)
    assert unknown.status_code == 404


def test_invitation_lifecycle_resend_revoke_and_distinct_errors(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    sa = _hdr(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    invited = client.post(
        f"{ADM}/users",
        headers=sa,
        json={
            "email": "new.reviewer@example.com",
            "full_name": "New Reviewer",
            "role": "partner_reviewer",
        },
    )
    assert invited.status_code == 201
    uid = invited.json()["data"]["id"]

    def state() -> str:
        return str(
            client.get(f"{ADM}/accounts/{uid}", headers=sa).json()["data"]["invitation_state"]
        )

    assert state() == "pending"
    first = last_token(email, "new.reviewer@example.com")
    assert "/activate?token=" in email.sent[-1].text  # the documented link shape
    revoked = client.post(f"{ADM}/accounts/{uid}/invitation/revoke", headers=sa)
    assert revoked.status_code == 200 and state() == "revoked"
    accept = f"{A}/invitations/accept"
    dead = client.post(accept, json={"token": first, "password": STRONG})
    assert dead.status_code == 400 and dead.json()["error"]["code"] == "TOKEN_REVOKED"
    again = client.get(f"{ADM}/accounts?invitation=revoked", headers=sa).json()["data"]
    assert uid in [a["id"] for a in again]

    assert client.post(f"{ADM}/accounts/{uid}/invitation/resend", headers=sa).status_code == 200
    second = last_token(email, "new.reviewer@example.com")
    assert second != first and state() == "pending"
    pending = client.get(f"{ADM}/accounts?invitation=pending", headers=sa).json()["data"]
    assert uid in [a["id"] for a in pending]

    db.execute(update(AuthToken).values(expires_at=utcnow() - timedelta(minutes=1)))
    db.commit()
    assert state() == "expired"
    expired = client.post(accept, json={"token": second, "password": STRONG})
    assert expired.json()["error"]["code"] == "TOKEN_EXPIRED"
    assert uid in [
        a["id"] for a in client.get(f"{ADM}/accounts?invitation=expired", headers=sa).json()["data"]
    ]

    client.post(f"{ADM}/accounts/{uid}/invitation/resend", headers=sa)
    third = last_token(email, "new.reviewer@example.com")
    assert client.post(accept, json={"token": third, "password": STRONG}).status_code == 200
    assert state() == "accepted"
    replay = client.post(accept, json={"token": third, "password": STRONG})
    assert replay.json()["error"]["code"] == "TOKEN_ALREADY_USED"
    for action in ("invitation/resend", "invitation/revoke"):
        r = client.post(f"{ADM}/accounts/{uid}/{action}", headers=sa)
        assert r.status_code == 409 and r.json()["error"]["code"] == "NOT_INVITED"
    for role in (StaffRole.BUSINESS_DEVELOPMENT_MANAGER, StaffRole.CONTENT_ADMINISTRATOR):
        h = _hdr(client, db, settings, role)
        assert client.post(f"{ADM}/accounts/{uid}/invitation/resend", headers=h).status_code == 403


def test_suspend_reactivate_and_admin_reset(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    admin_user = make_staff(db, settings, StaffRole.SUPER_ADMINISTRATOR)
    sa = bearer(login(client, admin_user.email)["access_token"])
    partner = onboard_partner(client, db, settings, email)
    pid = next(
        a["id"]
        for a in client.get(f"{ADM}/accounts?user_type=partner", headers=sa).json()["data"]
        if a["email"] == partner.email
    )
    me = next(
        a["id"]
        for a in client.get(f"{ADM}/accounts?user_type=staff", headers=sa).json()["data"]
        if a["email"] == admin_user.email
    )
    own = client.post(f"{ADM}/accounts/{me}/suspend", headers=sa)
    assert own.status_code == 409 and own.json()["error"]["code"] == "SELF_CHANGE"

    assert client.post(f"{ADM}/accounts/{pid}/password-reset", headers=sa).status_code == 200
    assert "/reset-password?token=" in email.sent[-1].text
    done = client.post(f"{ADM}/accounts/{pid}/suspend", headers=sa)
    assert done.status_code == 200 and done.json()["data"]["status"] == "deactivated"
    assert (
        client.get(f"{A}/me", headers=partner.headers).status_code == 401
    )  # signed out everywhere
    gone = client.post(f"{A}/login", json={"email": partner.email, "password": PASSWORD})
    assert gone.status_code == 403 and gone.json()["error"]["code"] == "ACCOUNT_DEACTIVATED"
    twice = client.post(f"{ADM}/accounts/{pid}/suspend", headers=sa)
    assert twice.status_code == 409
    assert client.post(f"{ADM}/accounts/{pid}/password-reset", headers=sa).status_code == 409
    back = client.post(f"{ADM}/accounts/{pid}/reactivate", headers=sa)
    assert back.status_code == 200 and back.json()["data"]["status"] == "active"
    assert login(client, partner.email)["access_token"]
    assert client.post(f"{ADM}/accounts/{pid}/reactivate", headers=sa).status_code == 409
    trail = client.get(f"{ADM}/accounts/{pid}", headers=sa).json()["data"]["recent_activity"]
    assert {"admin.account_suspended", "admin.account_reactivated"} <= {e["action"] for e in trail}


def test_self_and_last_super_admin_protections_hold(
    client: TestClient, db: Session, settings: Settings
) -> None:
    admin_user = make_staff(db, settings, StaffRole.SUPER_ADMINISTRATOR)
    sa = bearer(login(client, admin_user.email)["access_token"])
    for action, body in (
        ("role", {"role": "partner_reviewer"}),
        ("deactivate", None),
    ):
        r = client.post(f"{ADM}/users/{admin_user.id}/{action}", headers=sa, json=body)
        assert r.status_code == 409 and r.json()["error"]["code"] == "SELF_CHANGE"


def test_invitation_actions_are_rate_limited(
    app_factory: AppFactory, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    client = TestClient(app_factory(rate_limit_per_minute=2), raise_server_exceptions=False)
    sa = _hdr(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    uid = client.post(
        f"{ADM}/users",
        headers=sa,
        json={"email": "limit@example.com", "full_name": "Limit", "role": "partner_reviewer"},
    ).json()["data"]["id"]
    codes = [
        client.post(f"{ADM}/accounts/{uid}/invitation/resend", headers=sa).status_code
        for _ in range(4)
    ]
    assert codes[:2] == [200, 200] and 429 in codes
