"""Frontend requirements batch: staff user get/patch/activity and reviewer application workload."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.auth.constants import StaffRole
from tests.fakes import RecordingEmail
from tests.helpers import bearer, login, make_staff, onboard_partner, submitted_application

ADM = "/api/v1/admin"
R = "/api/v1/reviewer"


def _h(client: TestClient, db: Session, settings: Settings, role: StaffRole):  # type: ignore[no-untyped-def]
    user = make_staff(db, settings, role)
    return user, bearer(login(client, user.email)["access_token"])


def test_staff_user_get_patch_activity_and_authorization(
    client: TestClient, db: Session, settings: Settings
) -> None:
    _, sa = _h(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    target, _ = _h(client, db, settings, StaffRole.CONTENT_ADMINISTRATOR)
    bdm, bdm_h = _h(client, db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)

    got = client.get(f"{ADM}/users/{target.id}", headers=sa)
    assert got.status_code == 200 and got.json()["data"]["email"] == target.email

    patched = client.patch(
        f"{ADM}/users/{target.id}", json={"full_name": "Renamed Person"}, headers=sa
    )
    assert patched.status_code == 200 and patched.json()["data"]["full_name"] == "Renamed Person"
    assert (
        client.patch(f"{ADM}/users/{target.id}", json={"role": "x"}, headers=sa).status_code == 422
    )

    activity = client.get(f"{ADM}/users/{target.id}/activity", headers=sa)
    body = activity.json()
    assert activity.status_code == 200 and body["meta"]["total"] >= 1
    assert "admin.staff_profile_updated" in {r["action"] for r in body["data"]}

    for path in (f"{ADM}/users/{target.id}", f"{ADM}/users/{target.id}/activity"):
        assert client.get(path, headers=bdm_h).status_code == 403
    assert (
        client.patch(
            f"{ADM}/users/{target.id}", json={"full_name": "X Y"}, headers=bdm_h
        ).status_code
        == 403
    )
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"{ADM}/users/{missing}", headers=sa).status_code == 404
    assert client.get(f"{ADM}/users/{bdm.id}", headers=sa).status_code == 200


def test_application_workload_per_reviewer(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    _, sa = _h(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    reviewer, rev = _h(client, db, settings, StaffRole.PARTNER_REVIEWER)
    _, other = _h(client, db, settings, StaffRole.PARTNER_REVIEWER)
    bdm, bdm_h = _h(client, db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
    p = onboard_partner(client, db, settings, email)
    app_id = submitted_application(client, p)
    assert (
        client.post(
            f"{R}/applications/{app_id}/assign", json={"reviewer_id": str(reviewer.id)}, headers=sa
        ).status_code
        == 200
    )

    rows = client.get(f"{R}/workload", headers=sa).json()["data"]
    mine = [r for r in rows["rows"] if r["reviewer_id"] == str(reviewer.id)]
    assert mine and mine[0]["open_applications"] == 1 and mine[0]["by_status"] == {"submitted": 1}
    assert rows["total_open"] >= 1

    own = client.get(f"{R}/workload", headers=rev).json()["data"]
    assert [r["reviewer_id"] for r in own["rows"]] == [str(reviewer.id)]
    empty = client.get(f"{R}/workload", headers=other).json()["data"]
    assert empty == {"rows": [], "total_open": 0}
    assert client.get(f"{R}/workload", headers=bdm_h).status_code == 403
    assert client.get(f"{R}/workload").status_code == 401


def test_documents_report_not_scanned_never_clean(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    _, sa = _h(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    p = onboard_partner(client, db, settings, email)
    up = client.post(
        "/api/v1/partner/documents",
        headers=p.headers,
        data={"category": "registration_proof"},
        files={"file": ("reg.pdf", b"%PDF-1.4\n%%EOF\n", "application/pdf")},
    )
    assert up.status_code == 201, up.text
    version = up.json()["data"]["current_version"]
    assert version["upload_status"] == "quarantined" and version["scan_status"] == "not_scanned"
    rows = client.get(f"{ADM}/documents", headers=sa).json()["data"]
    assert rows and {r["scan_status"] for r in rows} == {"not_scanned"}
