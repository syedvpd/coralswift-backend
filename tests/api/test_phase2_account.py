"""PRD Phase 2 gap closure: account response, own-profile edit, sessions, MFA disable."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.auth import mfa
from app.modules.auth.constants import StaffRole
from app.modules.enquiries.models import Activity
from tests.fakes import RecordingEmail
from tests.helpers import PASSWORD, bearer, login, make_staff, onboard_partner

A = "/api/v1/auth"


def _code(secret: str, offset: int = 0) -> str:
    return mfa._hotp(secret, mfa.current_step() + offset)  # a code for a different time step


def _enable_mfa(client: TestClient, headers: dict[str, str]) -> str:
    secret = client.post(f"{A}/mfa/enroll", headers=headers).json()["data"]["secret"]
    assert (
        client.post(
            f"{A}/mfa/confirm", headers=headers, json={"code": _code(secret, -1)}
        ).status_code
        == 200
    )
    return str(secret)


def test_me_has_role_status_mfa_and_last_login(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    partner = onboard_partner(client, db, settings, email, org_name="Me Ltd")
    me = client.get(f"{A}/me", headers=partner.headers).json()["data"]
    assert me["user_type"] == "partner" and me["partner_role"] == "owner"
    assert me["account_status"] == "active" and me["organization"]["legal_name"] == "Me Ltd"
    assert me["mfa_enabled"] is False and me["mfa_required"] is False and me["phone"] is None
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


def test_partner_can_disable_mfa_with_password_and_code_staff_cannot(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    p = onboard_partner(client, db, settings, email)
    url = f"{A}/mfa/disable"
    assert (
        client.post(
            url, headers=p.headers, json={"password": PASSWORD, "code": "123456"}
        ).status_code
        == 409
    )
    secret = _enable_mfa(client, p.headers)
    again = client.post(f"{A}/mfa/enroll", headers=p.headers)
    assert (
        again.status_code == 409 and again.json()["error"]["code"] == "MFA_ALREADY_ENABLED"
    )  # no silent replace
    assert client.get(f"{A}/me", headers=p.headers).json()["data"]["mfa_enabled"] is True
    other = bearer(login(client, p.email)["access_token"])  # a second login needs the code now
    pending = client.post(f"{A}/mfa/verify", headers=other, json={"code": _code(secret, 0)})
    assert pending.status_code == 200

    wrong_pw = client.post(
        url, headers=p.headers, json={"password": "wrong-password-1", "code": _code(secret, 1)}
    )
    assert (
        wrong_pw.status_code == 400
        and wrong_pw.json()["error"]["code"] == "INVALID_CURRENT_PASSWORD"
    )
    wrong_code = client.post(url, headers=p.headers, json={"password": PASSWORD, "code": "000000"})
    assert wrong_code.status_code == 401
    assert client.get(f"{A}/me", headers=p.headers).json()["data"]["mfa_enabled"] is True
    good = client.post(
        url, headers=p.headers, json={"password": PASSWORD, "code": _code(secret, 1)}
    )
    assert good.status_code == 200, good.text
    assert client.get(f"{A}/me", headers=p.headers).json()["data"]["mfa_enabled"] is False
    assert client.get(f"{A}/me", headers=other).status_code == 401  # other sessions are signed out
    assert db.query(Activity).filter_by(action="auth.mfa_disabled").count() == 1
    assert client.post(f"{A}/mfa/enroll", headers=p.headers).status_code == 200  # can enrol again

    staff = make_staff(db, settings, StaffRole.PARTNER_REVIEWER)
    sh = bearer(login(client, staff.email)["access_token"])
    forbidden = client.post(url, headers=sh, json={"password": PASSWORD, "code": "123456"})
    assert (
        forbidden.status_code == 403
        and forbidden.json()["error"]["code"] == "MFA_REQUIRED_FOR_STAFF"
    )
    assert client.post(url, json={"password": PASSWORD, "code": "123456"}).status_code == 401
