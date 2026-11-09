"""MFA (TOTP) tests. Written during the development-only cycle; not executed yet."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.auth import mfa
from app.modules.auth.constants import StaffRole
from app.modules.auth.models import MfaRecoveryCode, User
from tests.conftest import AppFactory
from tests.fakes import RecordingEmail
from tests.helpers import PASSWORD, bearer, login, make_staff, onboard_partner

A = "/api/v1/auth"
R = "/api/v1/reviewer/applications"


def enrolled_reviewer(
    client: TestClient, db: Session, settings: Settings
) -> tuple[User, str, list[str]]:
    user = make_staff(db, settings, StaffRole.PARTNER_REVIEWER)
    tokens = login(client, user.email)
    assert tokens["mfa_enrollment_required"] is True
    h = bearer(tokens["access_token"])
    assert client.get(R, headers=h).json()["error"]["code"] == "MFA_ENROLLMENT_REQUIRED"
    secret = client.post(f"{A}/mfa/enroll", headers=h).json()["data"]["secret"]
    code = mfa.code_at(secret, mfa.current_step())
    codes = client.post(f"{A}/mfa/confirm", headers=h, json={"code": code}).json()["data"][
        "recovery_codes"
    ]
    assert client.get(R, headers=h).status_code == 200
    return user, secret, codes


def test_mfa_flow(app_factory: AppFactory, settings: Settings) -> None:
    app = app_factory(staff_mfa_required=True)
    with TestClient(app, raise_server_exceptions=False) as client:
        db: Session = app.state.sessionmaker()
        user, secret, codes = enrolled_reviewer(client, db, settings)
        assert len(codes) == 8
        stored = db.execute(select(User.mfa_secret_enc).where(User.id == user.id)).scalar_one()
        assert stored and secret not in stored  # secret encrypted at rest
        assert (
            db.execute(select(MfaRecoveryCode.code_hash)).scalars().first() not in codes
        )  # hashed
        # next login: valid password alone is not enough
        tokens = login(client, user.email)
        assert tokens["mfa_required"] is True
        h = bearer(tokens["access_token"])
        assert client.get(R, headers=h).json()["error"]["code"] == "MFA_REQUIRED"
        assert client.get(f"{A}/me", headers=h).status_code == 200  # pending sessions may see /me
        bad = client.post(f"{A}/mfa/verify", headers=h, json={"code": "000000"})
        assert bad.status_code == 401 and bad.json()["error"]["code"] == "INVALID_MFA_CODE"
        both = client.post(
            f"{A}/mfa/verify", headers=h, json={"code": "123456", "recovery_code": "x" * 10}
        )
        assert both.status_code == 422
        # the enrollment code was already used: replaying it is rejected
        replay = client.post(
            f"{A}/mfa/verify", headers=h, json={"code": mfa.code_at(secret, mfa.current_step())}
        )
        assert replay.status_code == 401
        nxt = mfa.code_at(
            secret, mfa.current_step() + 1
        )  # within the +1 window and newer than last_step
        assert client.post(f"{A}/mfa/verify", headers=h, json={"code": nxt}).status_code == 200
        assert client.get(R, headers=h).status_code == 200
        # refresh keeps the verified state
        new = client.post(f"{A}/refresh", json={"refresh_token": tokens["refresh_token"]}).json()[
            "data"
        ]
        assert client.get(R, headers=bearer(new["access_token"])).status_code == 200


def test_recovery_code_is_single_use(app_factory: AppFactory, settings: Settings) -> None:
    app = app_factory(staff_mfa_required=True)
    with TestClient(app, raise_server_exceptions=False) as client:
        db: Session = app.state.sessionmaker()
        user, _, codes = enrolled_reviewer(client, db, settings)
        h = bearer(login(client, user.email)["access_token"])
        assert (
            client.post(f"{A}/mfa/verify", headers=h, json={"recovery_code": codes[0]}).status_code
            == 200
        )
        h2 = bearer(login(client, user.email)["access_token"])
        assert (
            client.post(f"{A}/mfa/verify", headers=h2, json={"recovery_code": codes[0]}).status_code
            == 401
        )
        assert (
            client.post(f"{A}/mfa/verify", headers=h2, json={"recovery_code": codes[1]}).status_code
            == 200
        )


def test_repeated_wrong_codes_lock_the_account(app_factory: AppFactory, settings: Settings) -> None:
    app = app_factory(staff_mfa_required=True)
    with TestClient(app, raise_server_exceptions=False) as client:
        db: Session = app.state.sessionmaker()
        user, _, _ = enrolled_reviewer(client, db, settings)
        h = bearer(login(client, user.email)["access_token"])
        for _ in range(settings.login_max_failures):
            client.post(f"{A}/mfa/verify", headers=h, json={"code": "000000"})
        assert client.get(f"{A}/me", headers=h).status_code == 401  # sessions revoked
        assert (
            client.post(f"{A}/login", json={"email": user.email, "password": PASSWORD}).status_code
            == 401
        )


def test_enrollment_rules(app_factory: AppFactory, settings: Settings) -> None:
    app = app_factory(staff_mfa_required=True)
    with TestClient(app, raise_server_exceptions=False) as client:
        db: Session = app.state.sessionmaker()
        user = make_staff(db, settings, StaffRole.PARTNER_REVIEWER)
        h = bearer(login(client, user.email)["access_token"])
        assert (
            client.post(f"{A}/mfa/confirm", headers=h, json={"code": "123456"}).status_code == 409
        )  # not started
        assert (
            client.post(f"{A}/mfa/verify", headers=h, json={"code": "123456"}).status_code == 409
        )  # not enabled
        client.post(f"{A}/mfa/enroll", headers=h)
        assert (
            client.post(f"{A}/mfa/confirm", headers=h, json={"code": "000000"}).status_code == 401
        )
        assert (
            client.post(f"{A}/mfa/confirm", headers=h, json={"code": "12ab56"}).status_code == 422
        )
        assert client.post(f"{A}/mfa/enroll").status_code == 401  # needs a session


def test_partner_mfa_is_optional_but_enforced_once_enabled(
    app_factory: AppFactory, settings: Settings, email: RecordingEmail
) -> None:
    app = app_factory()
    with TestClient(app, raise_server_exceptions=False) as client:
        db: Session = app.state.sessionmaker()
        p = onboard_partner(client, db, settings, email)
        assert (
            client.get("/api/v1/partner/organization", headers=p.headers).status_code == 200
        )  # no MFA needed
        secret = client.post(f"{A}/mfa/enroll", headers=p.headers).json()["data"]["secret"]
        code = mfa.code_at(secret, mfa.current_step())
        assert (
            client.post(f"{A}/mfa/confirm", headers=p.headers, json={"code": code}).status_code
            == 200
        )
        fresh = bearer(login(client, p.email)["access_token"])
        assert (
            client.get("/api/v1/partner/organization", headers=fresh).json()["error"]["code"]
            == "MFA_REQUIRED"
        )


def test_totp_primitives() -> None:
    secret = mfa.new_secret()
    step = mfa.current_step()
    code = mfa.code_at(secret, step)
    assert mfa.verify_code(secret, code, None) == step
    assert mfa.verify_code(secret, code, step) is None  # replay
    assert mfa.verify_code(secret, "12345", None) is None
    # RFC 6238 test vector (SHA-1, secret "12345678901234567890", T=59 -> 94287082, last 6 digits)
    import base64

    rfc = base64.b32encode(b"12345678901234567890").decode()
    assert mfa.code_at(rfc, 59 // 30) == "287082"


def test_production_requires_staff_mfa() -> None:
    with pytest.raises(ValueError, match="STAFF_MFA_REQUIRED"):
        Settings(
            _env_file=None,
            app_env="production",
            database_url="postgresql+psycopg://u:p@localhost/x",
            secret_key="k" * 48,
            allowed_hosts=["a.com"],
            storage_backend="s3",
            s3_bucket="b",
            email_backend="brevo",
            brevo_api_key="k",
            email_sender_address="n@example.com",
            staff_mfa_required=False,
        )
