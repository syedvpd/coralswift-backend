"""PRD Phase 3 gap closure: staff in-app notification feed (own items only, no strategic leaks)."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.auth.constants import StaffRole
from tests import factories
from tests.fakes import RecordingEmail
from tests.helpers import bearer, login, make_staff, onboard_partner, submitted_application

FEED = "/api/v1/admin/feed"
ADM = "/api/v1/admin"


def _h(
    client: TestClient, db: Session, settings: Settings, role: StaffRole
) -> tuple[Any, dict[str, str]]:
    user = make_staff(db, settings, role)
    return user, bearer(login(client, user.email)["access_token"])


def test_feed_items_for_assignments_with_read_archive_and_isolation(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    sa_user, sa = _h(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    bdm_user, bdm = _h(client, db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
    reviewer_user, rev = _h(client, db, settings, StaffRole.PARTNER_REVIEWER)
    ref = client.post("/api/v1/enquiries/contact", json=factories.contact()).json()["data"][
        "reference_number"
    ]
    eid = next(
        r["id"]
        for r in client.get(f"{ADM}/enquiries", headers=sa).json()["data"]
        if r["reference_number"] == ref
    )

    client.post(f"{ADM}/enquiries/{eid}/assign", headers=sa, json={"user_id": str(bdm_user.id)})
    client.post(
        f"{ADM}/enquiries/{eid}/follow-ups",
        headers=sa,
        json={"note": "Call back", "assignee_id": str(bdm_user.id)},
    )
    partner = onboard_partner(client, db, settings, email, org_name="Feed Ltd")
    app_id = submitted_application(client, partner)
    client.post(
        f"/api/v1/reviewer/applications/{app_id}/assign",
        headers=sa,
        json={"reviewer_id": str(reviewer_user.id)},
    )
    client.post(
        f"{ADM}/enquiries/{eid}/assign", headers=sa, json={"user_id": str(sa_user.id)}
    )  # self: no item

    feed = client.get(FEED, headers=bdm).json()
    assert feed["meta"]["total"] == feed["meta"]["unread"] == 2
    assert {i["kind"] for i in feed["data"]} == {"enquiry_assigned", "followup_assigned"}
    assert all(
        ref in i["title"] and i["is_read"] is False and i["is_strategic"] is False
        for i in feed["data"]
    )
    assert client.get(FEED, headers=sa).json()["data"] == []  # nothing for the person who acted
    reviewer_items = client.get(FEED, headers=rev).json()["data"]
    assert [i["kind"] for i in reviewer_items] == ["application_assigned"]

    first = feed["data"][0]["id"]
    assert client.post(f"{FEED}/{first}/read", headers=bdm).json()["data"]["is_read"] is True
    assert client.post(f"{FEED}/{first}/read", headers=bdm).status_code == 200  # idempotent
    assert client.get(FEED, headers=bdm).json()["meta"]["unread"] == 1
    assert client.get(f"{FEED}?unread=true", headers=bdm).json()["meta"]["total"] == 1
    assert client.post(f"{FEED}/{first}/read", headers=rev).status_code == 404  # not theirs
    assert client.post(f"{FEED}/{first}/archive", headers=rev).status_code == 404
    assert client.post(f"{FEED}/{first}/read", headers=sa).status_code == 404

    archived = client.post(f"{FEED}/{first}/archive", headers=bdm).json()["data"]
    assert archived["archived_at"] is not None
    live = client.get(FEED, headers=bdm).json()
    assert live["meta"]["total"] == 1 and first not in [i["id"] for i in live["data"]]
    assert client.get(f"{FEED}?archived=true", headers=bdm).json()["meta"]["total"] == 1
    done = client.post(f"{FEED}/read-all", headers=bdm).json()["data"]
    assert done["marked"] == 1 and client.get(FEED, headers=bdm).json()["meta"]["unread"] == 0
    assert client.get(FEED).status_code == 401
    assert client.get(FEED, headers=partner.headers).status_code == 403  # staff feed only


def test_strategic_assignments_are_flagged_and_never_reach_other_roles(
    client: TestClient, db: Session, settings: Settings
) -> None:
    _, sa = _h(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    other_sa_user, other_sa = _h(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    bdm_user, bdm = _h(client, db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
    ref = client.post("/api/v1/enquiries/strategic", json=factories.strategic()).json()["data"][
        "reference_number"
    ]
    sid = client.get(f"{ADM}/enquiries?type=strategic", headers=sa).json()["data"][0]["id"]

    denied = client.post(
        f"{ADM}/enquiries/{sid}/assign", headers=sa, json={"user_id": str(bdm_user.id)}
    )
    assert denied.status_code == 422  # a BDM cannot own a strategic enquiry, so no feed item either
    ok = client.post(
        f"{ADM}/enquiries/{sid}/assign", headers=sa, json={"user_id": str(other_sa_user.id)}
    )
    assert ok.status_code == 200
    item = client.get(FEED, headers=other_sa).json()["data"][0]
    assert item["is_strategic"] is True and ref in item["title"]
    assert "TOP-SECRET" not in str(item)  # reference only, never submitter content
    assert client.get(FEED, headers=bdm).json()["data"] == []
    assert ref not in client.get(FEED, headers=bdm).text
