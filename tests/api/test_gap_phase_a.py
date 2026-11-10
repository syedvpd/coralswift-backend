"""Gap closure, phase A: authentication gaps, permission matrix, typed audit and outbox rows."""

from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.common.utilities import utcnow
from app.core.config import Settings
from app.modules.auth.constants import StaffRole
from app.modules.auth.models import AuthToken
from tests import factories
from tests.fakes import RecordingEmail
from tests.helpers import PASSWORD, bearer, last_token, login, make_staff, onboard_partner

A = "/api/v1/auth"
ADM = "/api/v1/admin"
NEW = "another-strong-passphrase-9"


def _staff(db: Session, settings: Settings, role: StaffRole) -> Any:
    return make_staff(db, settings, role)


def test_change_password_revokes_other_sessions(
    client: TestClient, db: Session, settings: Settings
) -> None:
    user = _staff(db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
    here = bearer(login(client, user.email)["access_token"])
    other = bearer(login(client, user.email)["access_token"])
    url = f"{A}/change-password"
    wrong = client.post(url, headers=here, json={"current_password": "nope", "new_password": NEW})
    assert wrong.status_code == 400 and wrong.json()["error"]["code"] == "INVALID_CURRENT_PASSWORD"
    same = client.post(
        url, headers=here, json={"current_password": PASSWORD, "new_password": PASSWORD}
    )
    assert same.status_code == 422 and same.json()["error"]["code"] == "PASSWORD_UNCHANGED"
    weak = client.post(url, headers=here, json={"current_password": PASSWORD, "new_password": "a"})
    assert weak.status_code == 422
    anonymous = client.post(url, json={"current_password": PASSWORD, "new_password": NEW})
    assert anonymous.status_code == 401
    ok = client.post(url, headers=here, json={"current_password": PASSWORD, "new_password": NEW})
    assert ok.status_code == 200
    assert client.get(f"{A}/me", headers=here).status_code == 200  # this session survives
    assert client.get(f"{A}/me", headers=other).status_code == 401  # the other one is gone
    old = client.post(f"{A}/login", json={"email": user.email, "password": PASSWORD})
    assert old.status_code == 401
    assert login(client, user.email, NEW)["access_token"]


def test_change_password_works_for_partners(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    p = onboard_partner(client, db, settings, email)
    r = client.post(
        f"{A}/change-password",
        headers=p.headers,
        json={"current_password": PASSWORD, "new_password": NEW},
    )
    assert r.status_code == 200
    assert login(client, p.email, NEW)["access_token"]


def test_one_time_tokens_report_why_they_fail(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    user = _staff(db, settings, StaffRole.CONTENT_ADMINISTRATOR)
    confirm = f"{A}/password-reset/confirm"

    def request_token() -> str:
        client.post(f"{A}/password-reset/request", json={"email": user.email})
        return last_token(email, user.email)

    def code(token: str) -> str:
        r = client.post(confirm, json={"token": token, "new_password": NEW})
        return str(r.json()["error"]["code"]) if r.status_code != 200 else "OK"

    first = request_token()
    second = request_token()  # supersedes the first
    assert code(first) == "TOKEN_REVOKED"
    assert code("cs_" + "x" * 40) == "INVALID_OR_EXPIRED_TOKEN"
    db.execute(update(AuthToken).values(expires_at=utcnow() - timedelta(minutes=1)))
    db.commit()
    assert code(second) == "TOKEN_EXPIRED"
    third = request_token()
    assert code(third) == "OK"
    assert code(third) == "TOKEN_ALREADY_USED"


def test_deactivated_account_is_named_only_with_the_right_password(
    client: TestClient, db: Session, settings: Settings
) -> None:
    admin = _staff(db, settings, StaffRole.SUPER_ADMINISTRATOR)
    target = _staff(db, settings, StaffRole.PARTNER_REVIEWER)
    h = bearer(login(client, admin.email)["access_token"])
    assert client.post(f"{ADM}/users/{target.id}/deactivate", headers=h).status_code == 200
    ok = client.post(f"{A}/login", json={"email": target.email, "password": PASSWORD})
    assert ok.status_code == 403 and ok.json()["error"]["code"] == "ACCOUNT_DEACTIVATED"
    bad = client.post(f"{A}/login", json={"email": target.email, "password": "wrong-password-1"})
    unknown = client.post(f"{A}/login", json={"email": "nobody@example.com", "password": PASSWORD})
    assert bad.status_code == unknown.status_code == 401
    assert bad.json() == unknown.json()  # nothing reveals that the account exists


def test_permission_matrix_matches_real_enforcement(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    heads = {
        role: bearer(login(client, _staff(db, settings, role).email)["access_token"])
        for role in StaffRole
    }
    sa = heads[StaffRole.SUPER_ADMINISTRATOR]
    data = client.get(f"{A}/permissions", headers=sa).json()["data"]
    matrix = data["role_matrix"]
    assert set(matrix) == {r.value for r in StaffRole}
    assert "admin/users" in matrix["super_administrator"]
    assert "admin/users" not in matrix["business_development_manager"]
    assert "admin/enquiries" in matrix["business_development_manager"]
    assert "reviewer/applications" in matrix["partner_reviewer"]
    assert "admin/content" in matrix["content_administrator"]
    assert "admin/enquiries" not in matrix["content_administrator"]
    bdm = client.get(f"{A}/permissions", headers=heads[StaffRole.BUSINESS_DEVELOPMENT_MANAGER])
    assert "role_matrix" not in bdm.json()["data"]  # only super administrators see the matrix

    table = client.app.state.permission_table  # type: ignore[attr-defined]
    probes = [
        e for e in table if e["kind"] == "staff" and e["method"] == "GET" and "{" not in e["path"]
    ]
    assert len(probes) >= 15
    for e in probes:  # the advertised matrix is exactly what the guards enforce
        for role, h in heads.items():
            status = client.get(e["path"], headers=h).status_code
            assert (status != 403) == (role.value in e["roles"]), (role, e["path"], status)

    partner = onboard_partner(client, db, settings, email)
    mine = client.get(f"{A}/permissions", headers=partner.headers).json()["data"]
    assert mine["account_type"] == "partner"
    assert all(not m["module"].startswith(("admin", "reviewer")) for m in mine["modules"])
    assert any(m["module"].startswith("partner") for m in mine["modules"])


def test_audit_rows_have_actor_names_strategic_flag_search_and_sort(
    client: TestClient, db: Session, settings: Settings
) -> None:
    admin = _staff(db, settings, StaffRole.SUPER_ADMINISTRATOR)
    h = bearer(login(client, admin.email)["access_token"])
    client.post("/api/v1/enquiries/strategic", json=factories.strategic())
    client.post("/api/v1/enquiries/contact", json=factories.contact())
    sid = client.get(f"{ADM}/enquiries?type=strategic", headers=h).json()["data"][0]["id"]
    client.patch(f"{ADM}/enquiries/{sid}", headers=h, json={"priority": "high"})
    rows = client.get(f"{ADM}/audit?page_size=100", headers=h).json()["data"]
    mine = [r for r in rows if r["actor_user_id"] == str(admin.id)]
    assert mine and all(r["actor_name"] == "Staff Member" for r in mine)
    enquiry_rows = [r for r in rows if r["record_type"] == "enquiry"]
    assert any(r["is_strategic"] for r in enquiry_rows)
    assert any(not r["is_strategic"] for r in enquiry_rows)
    by_q = client.get(f"{ADM}/audit?q=login", headers=h).json()
    assert by_q["data"] and all("login" in r["action"] for r in by_q["data"])
    asc = client.get(f"{ADM}/audit?sort=created_at&page_size=100", headers=h).json()["data"]
    desc = client.get(f"{ADM}/audit?sort=-created_at&page_size=100", headers=h).json()["data"]
    assert [r["id"] for r in asc] == [r["id"] for r in reversed(desc)]
    assert client.get(f"{ADM}/audit?sort=bogus", headers=h).status_code == 422


def test_outbox_rows_are_typed_filterable_and_flag_strategic(
    client: TestClient, db: Session, settings: Settings
) -> None:
    admin = _staff(db, settings, StaffRole.SUPER_ADMINISTRATOR)
    h = bearer(login(client, admin.email)["access_token"])
    client.post("/api/v1/enquiries/strategic", json=factories.strategic(business_email="s@x.org"))
    client.post("/api/v1/enquiries/contact", json=factories.contact(business_email="g@x.org"))
    body = client.get(f"{ADM}/notifications?status=all&page_size=100", headers=h).json()
    rows = body["data"]
    assert body["meta"]["total"] == len(rows) >= 2
    assert {"notification_type", "sent_at", "enquiry_id", "is_strategic"} <= set(rows[0])
    by_rcpt = {r["recipient"]: r for r in rows}
    assert by_rcpt["s@x.org"]["is_strategic"] is True
    assert by_rcpt["g@x.org"]["is_strategic"] is False
    only = client.get(f"{ADM}/notifications?status=all&q=g@x", headers=h).json()["data"]
    assert [r["recipient"] for r in only] == ["g@x.org"]
    tpl = by_rcpt["g@x.org"]["template"]
    same = client.get(f"{ADM}/notifications?status=all&template={tpl}", headers=h).json()["data"]
    assert same and all(r["template"] == tpl for r in same)
    future = (utcnow() + timedelta(days=1)).isoformat()
    none = client.get(
        f"{ADM}/notifications", params={"status": "all", "created_from": future}, headers=h
    ).json()
    assert none["data"] == [] and none["meta"]["total"] == 0
