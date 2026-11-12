"""PRD Phase 2 gap closure: account response, own-profile edit, sessions."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.auth.constants import StaffRole
from app.modules.enquiries.models import Activity
from tests.fakes import RecordingEmail
from tests.helpers import bearer, login, make_staff, onboard_partner

A = "/api/v1/auth"


def test_me_has_role_status_and_last_login(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    partner = onboard_partner(client, db, settings, email, org_name="Me Ltd")
    me = client.get(f"{A}/me", headers=partner.headers).json()["data"]
    assert me["user_type"] == "partner" and me["partner_role"] == "owner"
    assert me["account_status"] == "active" and me["organization"]["legal_name"] == "Me Ltd"
    assert "mfa_enabled" not in me and "mfa_required" not in me and me["phone"] is None
    assert me["last_login_at"] is not None
    assert not any(k in str(me).lower() for k in ("password", "secret", "hash", "token"))
    staff = make_staff(db, settings, StaffRole.CONTENT_ADMINISTRATOR)
    s = client.get(f"{A}/me", headers=bearer(login(client, staff.email)["access_token"])).json()[
        "data"
    ]
    assert s["user_type"] == "staff" and s["staff_role"] == "content_administrator"
    assert s["partner_role"] is None and s["organization"] is None
    assert client.get(f"{A}/me").status_code == 401


def test_patch_me_name_and_phone_validation_audit_and_isolation(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    a = onboard_partner(client, db, settings, email, org_name="Edit A Ltd")
    b = onboard_partner(client, db, settings, email, org_name="Edit B Ltd")
    ok = client.patch(
        f"{A}/me", headers=a.headers, json={"phone": "+14155550123", "full_name": "New Name"}
    )
    assert ok.status_code == 200 and ok.json()["data"]["phone"] == "+14155550123"
    assert (
        client.get(f"{A}/me", headers=b.headers).json()["data"]["phone"] is None
    )  # other account untouched
    for bad in (
        {"phone": "12345"},
        {"phone": "+1 415 555"},
        {"full_name": None},
        {},
        {"email": "x@y.z"},
        {"user_type": "staff"},
    ):
        assert client.patch(f"{A}/me", headers=a.headers, json=bad).status_code == 422, bad
    cleared = client.patch(f"{A}/me", headers=a.headers, json={"phone": None})
    assert cleared.status_code == 200 and cleared.json()["data"]["phone"] is None
    assert cleared.json()["data"]["full_name"] == "New Name"
    audits = db.query(Activity).filter_by(action="auth.profile_updated").all()
    assert audits and all(set(x.meta) == {"fields"} for x in audits)  # field names, never values
    assert "+14155550123" not in str([x.meta for x in audits])
    assert client.patch(f"{A}/me", json={"phone": "+14155550123"}).status_code == 401


def test_sessions_expose_expiry_and_sign_out_others(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    partner = onboard_partner(client, db, settings, email)
    other = bearer(login(client, partner.email)["access_token"])
    third = bearer(login(client, partner.email)["access_token"])
    rows = client.get(f"{A}/sessions", headers=other).json()["data"]
    assert (
        len(rows) >= 3
        and all(r["expires_at"] for r in rows)
        and sum(r["current"] for r in rows) == 1
    )
    stranger = onboard_partner(client, db, settings, email, org_name="Stranger Ltd")
    done = client.delete(f"{A}/sessions", headers=other)
    assert done.status_code == 200 and done.json()["data"]["revoked"] >= 2
    assert client.get(f"{A}/me", headers=other).status_code == 200  # this session stays
    assert client.get(f"{A}/me", headers=third).status_code == 401
    assert client.get(f"{A}/me", headers=partner.headers).status_code == 401
    assert (
        client.get(f"{A}/me", headers=stranger.headers).status_code == 200
    )  # other accounts untouched
    assert client.delete(f"{A}/sessions").status_code == 401
