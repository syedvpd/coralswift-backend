"""Gap closure: reviewer application list contract, allowed transitions, clearing assignment."""

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.common.utilities import utcnow
from app.core.config import Settings
from app.modules.auth.constants import StaffRole
from tests.fakes import RecordingEmail
from tests.helpers import (
    bearer,
    login,
    make_staff,
    onboard_partner,
    submitted_application,
)

R = "/api/v1/reviewer"
ADM = "/api/v1/admin"


def _h(client: TestClient, db: Session, settings: Settings, role: StaffRole):  # type: ignore[no-untyped-def]
    user = make_staff(db, settings, role)
    return user, bearer(login(client, user.email)["access_token"])


def test_reviewer_list_has_names_contacts_filters_sort_and_allowed_next(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    _, sa = _h(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    reviewer, rev = _h(client, db, settings, StaffRole.PARTNER_REVIEWER)
    _, other_rev = _h(client, db, settings, StaffRole.PARTNER_REVIEWER)
    p1 = onboard_partner(client, db, settings, email, org_name="Alpha Dispatch Ltd")
    p2 = onboard_partner(client, db, settings, email, org_name="Bravo Logistics Ltd")
    a1 = submitted_application(client, p1)
    a2 = submitted_application(client, p2)

    body = client.get(f"{R}/applications?page_size=100", headers=sa).json()
    assert body["meta"]["total"] == 2
    row = next(r for r in body["data"] if r["id"] == a1)
    assert row["updated_at"] and row["assigned_reviewer_name"] is None
    assert row["primary_contact"] and "email" in row["primary_contact"]
    assert set(row["allowed_next"]) >= {
        "eligibility_verification",
        "information_requested",
        "rejected",
    }
    assert "scale_up" not in row["allowed_next"]

    assert (
        client.post(
            f"{R}/applications/{a1}/assign", headers=sa, json={"reviewer_id": str(reviewer.id)}
        ).status_code
        == 200
    )
    mine = client.get(f"{R}/applications", headers=rev).json()
    assert [r["id"] for r in mine["data"]] == [a1] and mine["data"][0][
        "assigned_reviewer_name"
    ] == "Staff Member"
    assert client.get(f"{R}/applications", headers=other_rev).json()["data"] == []  # not theirs

    by_org = client.get(f"{R}/applications", params={"q": "bravo"}, headers=sa).json()
    assert [r["id"] for r in by_org["data"]] == [a2] and by_org["meta"]["total"] == 1
    ref = next(r["reference"] for r in body["data"] if r["id"] == a1)
    assert [
        r["id"]
        for r in client.get(f"{R}/applications", params={"q": ref.lower()}, headers=sa).json()[
            "data"
        ]
    ] == [a1]
    contact = row["primary_contact"]["email"]
    assert a1 in [
        r["id"]
        for r in client.get(f"{R}/applications", params={"q": contact}, headers=sa).json()["data"]
    ]
    assert client.get(f"{R}/applications?unassigned=true", headers=sa).json()["meta"]["total"] == 1
    assert (
        client.get(f"{R}/applications?assigned_reviewer_id={reviewer.id}", headers=sa).json()[
            "meta"
        ]["total"]
        == 1
    )
    future = (utcnow() + timedelta(days=1)).isoformat()
    for param in ("submitted_from", "updated_from"):
        empty = client.get(f"{R}/applications", params={param: future}, headers=sa).json()
        assert empty["data"] == [] and empty["meta"]["total"] == 0
    asc = client.get(f"{R}/applications?sort=reference", headers=sa).json()["data"]
    assert [r["reference"] for r in asc] == sorted(r["reference"] for r in asc)
    a = client.get(f"{R}/applications?sort=updated_at", headers=sa).json()["data"]
    d = client.get(f"{R}/applications?sort=-updated_at", headers=sa).json()["data"]
    assert [r["id"] for r in a] == [r["id"] for r in reversed(d)]
    assert client.get(f"{R}/applications?sort=password", headers=sa).status_code == 422
    assert client.get(f"{R}/applications?pathway=nonsense", headers=sa).status_code == 422
    path = client.get(f"{R}/applications?pathway=direct_project_engagement", headers=sa).json()
    assert path["meta"]["total"] in (0, 2)


def test_transition_table_matches_enforcement_and_is_reviewer_only(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    _, sa = _h(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    _, bdm = _h(client, db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
    table = client.get(f"{R}/transitions", headers=sa).json()["data"]
    assert client.get(f"{R}/transitions", headers=bdm).status_code == 403
    first = next(
        t for t in table if t["from"] == "submitted" and t["to"] == "eligibility_verification"
    )
    assert first["needs_assigned_reviewer"] is True and first["needs_reason"] is False
    decision = next(
        t for t in table if t["from"] == "commercial_legal_review" and t["to"] == "pilot_onboarding"
    )
    assert decision["needs_reason"] is True
    assert not any(t["to"] in ("draft", "submitted") for t in table)  # partner-only targets

    partner = onboard_partner(client, db, settings, email)
    app_id = submitted_application(client, partner)
    row = next(
        r for r in client.get(f"{R}/applications", headers=sa).json()["data"] if r["id"] == app_id
    )
    allowed = set(row["allowed_next"])
    for rule in table:  # what the list advertises is what the table says
        if rule["from"] == row["status"]:
            assert rule["to"] in allowed
    bad = client.post(
        f"{R}/applications/{app_id}/transition",
        headers=sa,
        json={"to_status": "scale_up", "reason": "x"},
    )
    assert bad.status_code in (409, 422)


def test_assignment_can_be_cleared_and_history_names_actors(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    _, sa = _h(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    reviewer, rev = _h(client, db, settings, StaffRole.PARTNER_REVIEWER)
    partner = onboard_partner(client, db, settings, email)
    app_id = submitted_application(client, partner)
    client.post(
        f"{R}/applications/{app_id}/assign", headers=sa, json={"reviewer_id": str(reviewer.id)}
    )
    assert client.get(f"{R}/applications/{app_id}", headers=rev).status_code == 200
    cleared = client.post(
        f"{R}/applications/{app_id}/assign", headers=sa, json={"reviewer_id": None}
    )
    assert cleared.status_code == 200 and cleared.json()["data"]["assigned_reviewer_id"] is None
    assert (
        client.get(f"{R}/applications/{app_id}", headers=rev).status_code == 404
    )  # access ends with it
    actions = [
        h["action"]
        for h in client.get(f"{R}/applications/{app_id}/history", headers=sa).json()["data"]
    ]
    assert "application.reviewer_cleared" in actions
    assert (
        client.post(
            f"{R}/applications/{app_id}/assign", headers=rev, json={"reviewer_id": None}
        ).status_code
        == 403
    )
    detail = client.get(f"{R}/applications/{app_id}", headers=sa).json()["data"]
    assert detail["application"]["updated_at"]
    assert all("actor_name" in h for h in detail["status_history"])
    assert any(h["actor_name"] for h in detail["status_history"])
