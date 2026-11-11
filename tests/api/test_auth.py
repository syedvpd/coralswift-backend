import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.common.utilities import utcnow
from app.core.config import Settings
from app.modules.auth.constants import StaffRole, UserStatus
from app.modules.auth.models import AuthSession, AuthToken, User
from app.modules.notifications.models import Notification
from tests.conftest import AppFactory
from tests.fakes import RecordingEmail
from tests.helpers import PASSWORD, bearer, last_token, login, make_staff, onboard_partner

A = "/api/v1/auth"


def test_invitation_flow_and_me(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    p = onboard_partner(client, db, settings, email, org_name="Acme Ltd")
    me = client.get(f"{A}/me", headers=p.headers).json()["data"]
    assert me["user_type"] == "partner" and me["organization"]["legal_name"] == "Acme Ltd"
    assert me["organization"]["id"] == p.organization_id
    # token hash stored, plaintext never stored; link scrubbed from outbox after delivery
    user = db.execute(select(User).where(User.email == p.email)).scalar_one()
    assert (
        user.status is UserStatus.ACTIVE
        and user.password_hash
        and PASSWORD not in user.password_hash
    )
    assert user.password_hash.startswith("$argon2id$")
    tokens = db.execute(select(AuthToken)).scalars().all()
    assert all(t.token_hash.startswith("cs_") is False and len(t.token_hash) == 64 for t in tokens)
    outbox = db.execute(select(Notification)).scalars().all()
    assert all("link" not in n.context for n in outbox)


def test_invitation_token_is_single_use_and_policy_checked(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    admin = make_staff(db, settings, StaffRole.SUPER_ADMINISTRATOR)
    h = bearer(login(client, admin.email)["access_token"])
    client.post(
        "/api/v1/reviewer/invitations",
        headers=h,
        json={
            "email": "new@example.com",
            "full_name": "N",
            "new_organization_legal_name": "N Ltd",
        },
    )
    token = last_token(email, "new@example.com")
    weak = client.post(f"{A}/invitations/accept", json={"token": token, "password": "short"})
    assert weak.status_code == 422 and weak.json()["error"]["code"] == "WEAK_PASSWORD"
    assert (
        client.post(
            f"{A}/invitations/accept", json={"token": token, "password": PASSWORD}
        ).status_code
        == 200
    )
    replay = client.post(f"{A}/invitations/accept", json={"token": token, "password": PASSWORD})
    assert replay.status_code == 400 and replay.json()["error"]["code"] == "TOKEN_ALREADY_USED"
    assert (
        client.post(
            f"{A}/invitations/accept", json={"token": "cs_bogus_token_value", "password": PASSWORD}
        ).status_code
        == 400
    )


def test_expired_invitation_rejected(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    admin = make_staff(db, settings, StaffRole.SUPER_ADMINISTRATOR)
    h = bearer(login(client, admin.email)["access_token"])
    client.post(
        "/api/v1/reviewer/invitations",
        headers=h,
        json={
            "email": "late@example.com",
            "full_name": "L",
            "new_organization_legal_name": "L Ltd",
        },
    )
    db.execute(update(AuthToken).values(expires_at=utcnow() - timedelta(seconds=1)))
    db.commit()
    r = client.post(
        f"{A}/invitations/accept",
        json={"token": last_token(email, "late@example.com"), "password": PASSWORD},
    )
    assert r.status_code == 400


def test_only_super_admin_can_invite(client: TestClient, db: Session, settings: Settings) -> None:
    reviewer = make_staff(db, settings, StaffRole.PARTNER_REVIEWER)
    body = {"email": "x@example.com", "full_name": "X", "new_organization_legal_name": "X Ltd"}
    assert client.post("/api/v1/reviewer/invitations", json=body).status_code == 401
    h = bearer(login(client, reviewer.email)["access_token"])
    assert client.post("/api/v1/reviewer/invitations", headers=h, json=body).status_code == 403


def test_login_errors_are_generic(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    p = onboard_partner(client, db, settings, email)
    bodies = set()
    for creds in (
        {"email": p.email, "password": "wrong-password-123"},
        {"email": "nobody@example.com", "password": PASSWORD},
    ):
        r = client.post(f"{A}/login", json=creds)
        assert r.status_code == 401 and r.json()["error"]["code"] == "INVALID_CREDENTIALS"
        bodies.add(r.text)
    assert len(bodies) == 1


def test_lockout_after_repeated_failures_even_with_correct_password(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    p = onboard_partner(client, db, settings, email)
    for _ in range(settings.login_max_failures):
        assert (
            client.post(
                f"{A}/login", json={"email": p.email, "password": "bad-password-xyz"}
            ).status_code
            == 401
        )
    locked = client.post(f"{A}/login", json={"email": p.email, "password": PASSWORD})
    assert locked.status_code == 423 and locked.json()["error"]["code"] == "ACCOUNT_LOCKED"
    still_generic = client.post(
        f"{A}/login", json={"email": p.email, "password": "bad-password-xyz"}
    )
    assert still_generic.status_code == 401
    assert still_generic.json()["error"]["code"] == "INVALID_CREDENTIALS"
    db.execute(
        update(User)
        .where(User.email == p.email)
        .values(locked_until=utcnow() - timedelta(seconds=1))
    )
    db.commit()
    assert (
        client.post(f"{A}/login", json={"email": p.email, "password": PASSWORD}).status_code == 200
    )


def test_protected_routes_need_valid_token(client: TestClient) -> None:
    assert client.get(f"{A}/me").status_code == 401
    r = client.get(f"{A}/me", headers=bearer("cs_not_a_real_token"))
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"


def test_logout_revokes_token(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    p = onboard_partner(client, db, settings, email)
    assert client.post(f"{A}/logout", headers=p.headers).status_code == 200
    assert client.get(f"{A}/me", headers=p.headers).status_code == 401


def test_expired_access_token_rejected(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    p = onboard_partner(client, db, settings, email)
    db.execute(update(AuthSession).values(access_expires_at=utcnow() - timedelta(seconds=1)))
    db.commit()
    assert client.get(f"{A}/me", headers=p.headers).status_code == 401


def test_refresh_rotation_and_replay_revokes_session(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    p = onboard_partner(client, db, settings, email)
    old_refresh = p.tokens["refresh_token"]
    new = client.post(f"{A}/refresh", json={"refresh_token": old_refresh}).json()["data"]
    assert new["refresh_token"] != old_refresh
    assert client.get(f"{A}/me", headers=bearer(new["access_token"])).status_code == 200
    assert client.get(f"{A}/me", headers=p.headers).status_code == 401  # old access token replaced
    replay = client.post(f"{A}/refresh", json={"refresh_token": old_refresh})  # token replay
    assert replay.status_code == 401
    assert (
        client.get(f"{A}/me", headers=bearer(new["access_token"])).status_code == 401
    )  # session killed
    assert (
        client.post(f"{A}/refresh", json={"refresh_token": new["refresh_token"]}).status_code == 401
    )


def test_deactivated_account_old_token_fails(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    p = onboard_partner(client, db, settings, email)
    db.execute(update(User).where(User.email == p.email).values(status=UserStatus.DEACTIVATED))
    db.commit()
    assert client.get(f"{A}/me", headers=p.headers).status_code == 401
    assert (
        client.post(f"{A}/refresh", json={"refresh_token": p.tokens["refresh_token"]}).status_code
        == 401
    )
    login_again = client.post(f"{A}/login", json={"email": p.email, "password": PASSWORD})
    assert login_again.status_code == 403  # right password: the account is named as deactivated
    assert login_again.json()["error"]["code"] == "ACCOUNT_DEACTIVATED"


def test_sessions_list_and_revoke(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    p = onboard_partner(client, db, settings, email)
    second = login(client, p.email)
    sessions = client.get(f"{A}/sessions", headers=p.headers).json()["data"]
    assert len(sessions) == 2 and sum(s["current"] for s in sessions) == 1
    other = next(s for s in sessions if not s["current"])
    assert client.delete(f"{A}/sessions/{other['id']}", headers=p.headers).status_code == 200
    assert client.get(f"{A}/me", headers=bearer(second["access_token"])).status_code == 401
    assert client.delete(f"{A}/sessions/{uuid.uuid4()}", headers=p.headers).status_code == 404


def test_password_reset_flow_and_abuse(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    p = onboard_partner(client, db, settings, email)
    known = client.post(f"{A}/password-reset/request", json={"email": p.email})
    unknown = client.post(f"{A}/password-reset/request", json={"email": "ghost@example.com"})
    assert known.status_code == unknown.status_code == 202 and known.text == unknown.text
    assert not any(m.to == "ghost@example.com" for m in email.sent)
    token = last_token(email, p.email)
    new_pw = "another-strong-passphrase-9"
    assert (
        client.post(
            f"{A}/password-reset/confirm", json={"token": token, "new_password": "short"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"{A}/password-reset/confirm", json={"token": token, "new_password": new_pw}
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"{A}/password-reset/confirm", json={"token": token, "new_password": new_pw}
        ).status_code
        == 400
    )  # single use
    assert client.get(f"{A}/me", headers=p.headers).status_code == 401  # old sessions revoked
    assert (
        client.post(f"{A}/login", json={"email": p.email, "password": PASSWORD}).status_code == 401
    )
    assert client.post(f"{A}/login", json={"email": p.email, "password": new_pw}).status_code == 200


def test_new_reset_request_supersedes_older_token(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    p = onboard_partner(client, db, settings, email)
    client.post(f"{A}/password-reset/request", json={"email": p.email})
    first = last_token(email, p.email)
    client.post(f"{A}/password-reset/request", json={"email": p.email})
    second = last_token(email, p.email)
    assert first != second
    assert (
        client.post(
            f"{A}/password-reset/confirm",
            json={"token": first, "new_password": "yet-another-pass-77"},
        ).status_code
        == 400
    )
    assert (
        client.post(
            f"{A}/password-reset/confirm",
            json={"token": second, "new_password": "yet-another-pass-77"},
        ).status_code
        == 200
    )


def test_secrets_never_in_logs(
    client: TestClient,
    db: Session,
    settings: Settings,
    email: RecordingEmail,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    caplog.set_level(logging.DEBUG)
    p = onboard_partner(client, db, settings, email)
    client.post(f"{A}/login", json={"email": p.email, "password": "bad-password-xyz"})
    text = caplog.text
    assert PASSWORD not in text and "bad-password-xyz" not in text
    assert p.tokens["access_token"] not in text and p.tokens["refresh_token"] not in text


def test_login_rate_limited(app_factory: AppFactory, email: RecordingEmail) -> None:
    with TestClient(app_factory(rate_limit_per_minute=2), raise_server_exceptions=False) as c:
        codes = [
            c.post(f"{A}/login", json={"email": "a@example.com", "password": "x"}).status_code
            for _ in range(3)
        ]
        assert codes == [401, 401, 429]
