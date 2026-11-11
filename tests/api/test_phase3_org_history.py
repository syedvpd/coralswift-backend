"""Phase 2/3 gap closure: organisation history for staff, change-request diff, partner messages."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.auth.constants import StaffRole
from tests import factories
from tests.fakes import RecordingEmail
from tests.helpers import bearer, login, make_staff, onboard_partner

ADM = "/api/v1/admin"
P = "/api/v1/partner"


def _h(client: TestClient, db: Session, settings: Settings, role: StaffRole) -> dict[str, str]:
    return bearer(login(client, make_staff(db, settings, role).email)["access_token"])


def test_staff_see_revisions_activity_and_change_request_before_values(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    sa = _h(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    bdm = _h(client, db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
    cms = _h(client, db, settings, StaffRole.CONTENT_ADMINISTRATOR)
    p = onboard_partner(client, db, settings, email, org_name="History Ltd")
    org_id = p.organization_id
    assert (
        client.put(
            f"{P}/organization", headers=p.headers, json={"website": "https://old.example"}
        ).status_code
        == 200
    )
    direct = client.put(
        f"{P}/organization", headers=p.headers, json={"website": "https://new.example"}
    )
    assert direct.status_code == 409 and direct.json()["error"]["code"] == "CHANGE_REQUEST_REQUIRED"
    first = client.post(
        f"{P}/organization/change-requests",
        headers=p.headers,
        json={"changes": {"website": "https://new.example"}, "reason": "Moved"},
    )
    assert first.status_code == 201
    assert (
        client.post(
            f"{ADM}/profile-change-requests/{first.json()['data']['id']}/decide",
            headers=sa,
            json={"approve": True},
        ).status_code
        == 200
    )

    rev = client.get(f"{ADM}/organizations/{org_id}/revisions", headers=bdm).json()
    assert rev["meta"]["total"] >= 2
    latest = rev["data"][0]
    assert latest["changes"]["website"] == {
        "old": "https://old.example",
        "new": "https://new.example",
    }
    assert latest["changed_by_name"] == "Partner User" or latest["changed_by_name"]
    act = client.get(f"{ADM}/organizations/{org_id}/activity", headers=bdm).json()
    assert act["meta"]["total"] == len(act["data"]) >= 1
    assert client.get(f"{ADM}/organizations/{org_id}/activity", headers=cms).status_code == 403
    assert (
        client.get(f"{ADM}/organizations/{org_id}/revisions", headers=p.headers).status_code == 403
    )
    assert (
        client.get(
            f"{ADM}/organizations/00000000-0000-0000-0000-000000000000/revisions", headers=sa
        ).status_code
        == 404
    )

    created = client.post(
        f"{P}/organization/change-requests",
        headers=p.headers,
        json={"changes": {"website": "https://requested.example"}, "reason": "Rebrand"},
    )
    assert created.status_code == 201, created.text
    pending = client.get(f"{ADM}/profile-change-requests", headers=sa).json()["data"][0]
    assert pending["organization_name"] == "History Ltd"
    assert pending["before"] == {"website": "https://new.example"}  # what staff would overwrite
    assert pending["changes"] == {"website": "https://requested.example"}
    decided = client.post(
        f"{ADM}/profile-change-requests/{pending['id']}/decide", headers=sa, json={"approve": True}
    )
    assert decided.status_code == 200
    after = client.get(f"{ADM}/organizations/{org_id}/revisions", headers=sa).json()["data"][0]
    assert after["changes"]["website"] == {
        "old": "https://new.example",
        "new": "https://requested.example",
    }
    assert (
        client.get(f"{ADM}/profile-change-requests?status=approved", headers=sa).json()["data"][0][
            "before"
        ]
        == {}
    )


def test_strategic_events_never_appear_in_organisation_activity(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    bdm = _h(client, db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
    p = onboard_partner(client, db, settings, email, org_name="Strategic Ltd")
    client.post("/api/v1/enquiries/strategic", json=factories.strategic(business_email=p.email))
    body = client.get(
        f"{ADM}/organizations/{p.organization_id}/activity?page_size=100", headers=bdm
    ).text
    assert "TOP-SECRET" not in body
    for row in client.get(
        f"{ADM}/organizations/{p.organization_id}/activity?page_size=100", headers=bdm
    ).json()["data"]:
        assert row["record_type"] != "enquiry" or "strategic" not in str(row["meta"]).lower()


def test_partner_messages_have_title_category_reference_and_unread_controls(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    a = onboard_partner(client, db, settings, email, org_name="Msg A Ltd")
    b = onboard_partner(client, db, settings, email, org_name="Msg B Ltd")
    client.post("/api/v1/enquiries/contact", json=factories.contact(business_email=a.email))
    feed = client.get(f"{P}/notifications", headers=a.headers).json()
    item = feed["data"][0]
    assert item["title"] and item["category"] in (
        "acknowledgement",
        "application",
        "account",
        "other",
    )
    assert item["related_reference"] is None or item["related_reference"].startswith("CS-")
    assert client.get(f"{P}/notifications/unread-count", headers=a.headers).json()["data"] == {
        "unread": feed["meta"]["unread"]
    }
    client.post(f"{P}/notifications/{item['id']}/read", headers=a.headers)
    assert (
        client.get(f"{P}/notifications/unread-count", headers=a.headers).json()["data"]["unread"]
        == feed["meta"]["unread"] - 1
    )
    back = client.post(f"{P}/notifications/{item['id']}/unread", headers=a.headers)
    assert back.status_code == 200 and back.json()["data"]["is_read"] is False
    assert (
        client.post(f"{P}/notifications/{item['id']}/unread", headers=b.headers).status_code == 404
    )
    assert client.get(f"{P}/notifications/unread-count").status_code == 401
