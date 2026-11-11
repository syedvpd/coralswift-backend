"""Malware scanner integration (fail-closed), ACCOUNT_NOT_ACTIVATED, writable lockout policy."""

import socket
import struct
import threading
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.integrations import scanner as scanner_mod
from app.integrations.scanner import ClamAVScanner, ScanResult
from app.modules.auth.constants import StaffRole
from app.modules.documents import constants as doc_constants
from tests import factories
from tests.fakes import RecordingEmail
from tests.helpers import PASSWORD, bearer, login, make_staff, onboard_partner

P = "/api/v1/partner"
R = "/api/v1/reviewer"
ADM = "/api/v1/admin"


def _fake_clamd(reply: bytes) -> tuple[int, threading.Thread]:
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    def serve() -> None:
        conn, _ = srv.accept()
        with conn:
            assert conn.recv(10) == b"zINSTREAM\0"
            data = b""
            while True:
                header = b""
                while len(header) < 4:
                    header += conn.recv(4 - len(header))
                (size,) = struct.unpack(">I", header)
                if size == 0:
                    break
                got = 0
                while got < size:
                    part = conn.recv(size - got)
                    got += len(part)
                    data += part
            conn.sendall(reply)
        srv.close()

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    return port, t


def test_clamav_client_speaks_instream_and_fails_closed() -> None:
    port, t = _fake_clamd(b"stream: OK\0")
    assert ClamAVScanner("127.0.0.1", port, 5).scan(b"hello" * 50_000).verdict == "clean"
    t.join(5)
    port, t = _fake_clamd(b"stream: Eicar-Test-Signature FOUND\0")
    found = ClamAVScanner("127.0.0.1", port, 5).scan(b"x")
    assert found.verdict == "infected" and "Eicar" in found.detail
    t.join(5)
    port, t = _fake_clamd(b"INSTREAM size limit exceeded. ERROR\0")
    assert ClamAVScanner("127.0.0.1", port, 5).scan(b"x").verdict == "error"
    t.join(5)
    free = socket.socket()
    free.bind(("127.0.0.1", 0))
    closed_port = free.getsockname()[1]
    free.close()
    assert ClamAVScanner("127.0.0.1", closed_port, 1).scan(b"x").verdict == "error"


class _Fixed:
    def __init__(self, verdict: str) -> None:
        self.verdict = verdict

    def scan(self, data: bytes) -> ScanResult:
        return ScanResult(self.verdict)  # type: ignore[arg-type]


def _use_scanner(monkeypatch: pytest.MonkeyPatch, verdict: str | None) -> None:
    monkeypatch.setattr(scanner_mod, "_active", None if verdict is None else _Fixed(verdict))
    monkeypatch.setitem(doc_constants._state, "enforce_clean", verdict is not None)


def _upload(client: TestClient, p: Any) -> dict[str, Any]:
    r = client.post(
        f"{P}/documents",
        headers=p.headers,
        data={"category": "registration_proof"},
        files={"file": ("a.pdf", factories.PDF)},
    )
    assert r.status_code == 201, r.text
    return dict(r.json()["data"])


def test_scanner_states_block_download_and_review_until_clean(
    client: TestClient,
    db: Session,
    settings: Settings,
    email: RecordingEmail,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.helpers import submitted_application

    p = onboard_partner(client, db, settings, email)
    app_id = submitted_application(client, p)
    sa_user = make_staff(db, settings, StaffRole.SUPER_ADMINISTRATOR)
    sa = bearer(login(client, sa_user.email)["access_token"])
    client.post(
        f"{R}/applications/{app_id}/assign", headers=sa, json={"reviewer_id": str(sa_user.id)}
    )

    # no scanner: quarantine-only, honestly reported
    _use_scanner(monkeypatch, None)
    plain = _upload(client, p)
    assert plain["current_version"]["scan_status"] == "not_scanned"
    assert client.get(f"{P}/documents/{plain['id']}/download", headers=p.headers).status_code == 200

    # scanner says clean
    _use_scanner(monkeypatch, "clean")
    ok = _upload(client, p)
    assert ok["current_version"]["scan_status"] == "clean"
    assert client.get(f"{P}/documents/{ok['id']}/download", headers=p.headers).status_code == 200
    review = f"{R}/applications/{app_id}/documents/{ok['id']}/review"
    assert client.post(review, headers=sa, json={"status": "accepted"}).status_code == 200

    # infected: stored but never downloadable or reviewable
    _use_scanner(monkeypatch, "infected")
    bad = _upload(client, p)
    assert bad["current_version"]["scan_status"] == "infected"
    assert client.get(f"{P}/documents/{bad['id']}/download", headers=p.headers).status_code == 404
    blocked = client.post(
        f"{R}/applications/{app_id}/documents/{bad['id']}/review",
        headers=sa,
        json={"status": "accepted"},
    )
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "SCAN_REQUIRED"

    # scanner down: fails closed
    _use_scanner(monkeypatch, "error")
    down = _upload(client, p)
    assert down["current_version"]["scan_status"] == "scan_failed"
    assert client.get(f"{P}/documents/{down['id']}/download", headers=p.headers).status_code == 404

    # a previously stored quarantined file is "scan_pending" once a scanner is mandatory
    _use_scanner(monkeypatch, "clean")
    listing = client.get(f"{P}/documents", headers=p.headers).json()["data"]
    by_id = {d["id"]: d["current_version"]["scan_status"] for d in listing}
    assert by_id[plain["id"]] == "scan_pending"
    assert by_id[ok["id"]] == "clean"


def test_invited_account_gets_not_activated_error_wrong_password_stays_generic(
    client: TestClient, db: Session, settings: Settings
) -> None:
    sa_user = make_staff(db, settings, StaffRole.SUPER_ADMINISTRATOR)
    sa = bearer(login(client, sa_user.email)["access_token"])
    inv = client.post(
        f"{R}/invitations",
        headers=sa,
        json={
            "email": "pending.person@example.com",
            "full_name": "Pending Person",
            "new_organization_legal_name": "Pending Org",
        },
    )
    assert inv.status_code == 201
    r = client.post(
        "/api/v1/auth/login", json={"email": "pending.person@example.com", "password": PASSWORD}
    )
    assert r.status_code == 403 and r.json()["error"]["code"] == "ACCOUNT_NOT_ACTIVATED"
    unknown = client.post(
        "/api/v1/auth/login", json={"email": "nobody.here@example.com", "password": PASSWORD}
    )
    assert unknown.status_code == 401 and unknown.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_lockout_threshold_is_a_writable_security_policy(
    client: TestClient, db: Session, settings: Settings
) -> None:
    sa_user = make_staff(db, settings, StaffRole.SUPER_ADMINISTRATOR)
    sa = bearer(login(client, sa_user.email)["access_token"])
    victim = make_staff(db, settings, StaffRole.PARTNER_REVIEWER)
    key = f"{ADM}/settings/security.login_max_failures"
    assert client.put(key, headers=sa, json={"value": "2"}).status_code == 422  # below the floor
    assert client.put(key, headers=sa, json={"value": "4"}).status_code == 200
    try:
        # the environment default (3) would lock now; the written policy (4) does not
        for _ in range(3):
            wrong = {"email": victim.email, "password": "wrong-password-1"}
            assert client.post("/api/v1/auth/login", json=wrong).status_code == 401
        still_ok = client.post(
            "/api/v1/auth/login", json={"email": victim.email, "password": PASSWORD}
        )
        assert still_ok.status_code == 200
        for _ in range(4):
            wrong = {"email": victim.email, "password": "wrong-password-1"}
            client.post("/api/v1/auth/login", json=wrong)
        locked = client.post(
            "/api/v1/auth/login", json={"email": victim.email, "password": PASSWORD}
        )
        assert locked.status_code == 423 and locked.json()["error"]["code"] == "ACCOUNT_LOCKED"
    finally:
        client.delete(key, headers=sa)
