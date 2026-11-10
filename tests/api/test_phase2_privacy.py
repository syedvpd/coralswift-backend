"""PRD Phase 2 gap closure: authenticated partner privacy requests."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.auth.constants import StaffRole
from tests.fakes import RecordingEmail
from tests.helpers import bearer, login, make_staff, onboard_partner

URL = "/api/v1/partner/privacy-requests"
ADM = "/api/v1/admin/privacy-requests"


def test_partner_privacy_requests_use_the_session_identity(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    a = onboard_partner(client, db, settings, email, org_name="Priv A Ltd")
    b = onboard_partner(client, db, settings, email, org_name="Priv B Ltd")
    sa = bearer(
        login(client, make_staff(db, settings, StaffRole.SUPER_ADMINISTRATOR).email)["access_token"]
    )

    made = client.post(
        URL, headers=a.headers, json={"kind": "access", "details": "Send me my data"}
    )
    assert made.status_code == 201, made.text
    body = made.json()["data"]
    assert body["reference"].startswith("PR-") and body["status"] == "received"
    assert a.email not in str(body) and "email" not in body  # identity is never echoed or accepted
    for bad in ({"kind": "access", "email": "victim@example.com"}, {"kind": "nonsense"}, {}):
        assert client.post(URL, headers=a.headers, json=bad).status_code == 422, bad
    assert client.post(URL, json={"kind": "access"}).status_code == 401
    assert client.post(URL, headers=sa, json={"kind": "access"}).status_code == 403  # partners only

    mine = client.get(URL, headers=a.headers).json()
    assert mine["meta"]["total"] == 1 and mine["data"][0]["reference"] == body["reference"]
    assert (
        client.get(URL, headers=b.headers).json()["data"] == []
    )  # other organisations see nothing
    assert client.get(URL, headers=sa).status_code == 403

    row = client.get(ADM, headers=sa).json()["data"][0]
    assert (
        row["email"] == a.email
        and row["email_verified"] is True
        and row["submitted_by_partner"] is True
    )
    done = client.post(f"{ADM}/{row['id']}", headers=sa, json={"status": "in_progress"})
    assert done.status_code == 200  # no email link needed: the session already proved identity
    note = "Internal: check legal hold first"
    client.post(
        f"{ADM}/{row['id']}", headers=sa, json={"status": "in_progress", "resolution_note": note}
    )
    open_view = client.get(URL, headers=a.headers).json()["data"][0]
    assert open_view["resolution_note"] is None and open_view["status"] == "in_progress"
    client.post(
        f"{ADM}/{row['id']}",
        headers=sa,
        json={"status": "completed", "resolution_note": "Data sent by post"},
    )
    closed = client.get(URL, headers=a.headers).json()["data"][0]
    assert closed["status"] == "completed" and closed["resolution_note"] == "Data sent by post"
