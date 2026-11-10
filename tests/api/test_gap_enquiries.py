"""Gap closure: enquiry list contract, follow-up kinds/owner/cancel, global follow-ups, activity."""

from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.utilities import utcnow
from app.core.config import Settings
from app.modules.auth.constants import StaffRole
from app.modules.enquiries.models import Enquiry
from tests import factories
from tests.helpers import bearer, login, make_staff

ADM = "/api/v1/admin"
PUB = "/api/v1/enquiries"


def _h(
    client: TestClient, db: Session, settings: Settings, role: StaffRole
) -> tuple[Any, dict[str, str]]:
    user = make_staff(db, settings, role)
    return user, bearer(login(client, user.email)["access_token"])


def _ids(client: TestClient, h: dict[str, str]) -> dict[str, str]:
    """reference -> id for everything the caller may see."""
    rows = client.get(f"{ADM}/enquiries?page_size=100", headers=h).json()["data"]
    return {r["reference_number"]: r["id"] for r in rows}


def test_enquiry_rows_carry_names_phone_category_and_filter_server_side(
    client: TestClient, db: Session, settings: Settings
) -> None:
    sa_user, sa = _h(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    bdm_user, bdm = _h(client, db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
    proj = client.post(f"{PUB}/project", json=factories.project()).json()["data"][
        "reference_number"
    ]
    client.post(f"{PUB}/contact", json=factories.contact())
    ids = _ids(client, sa)
    client.post(
        f"{ADM}/enquiries/{ids[proj]}/assign", headers=sa, json={"user_id": str(bdm_user.id)}
    )

    rows = client.get(f"{ADM}/enquiries?page_size=100", headers=sa).json()["data"]
    row = next(r for r in rows if r["reference_number"] == proj)
    assert row["contact_phone"].startswith("+") and row["updated_at"]
    assert row["assigned_user_name"] == "Staff Member" and row["category"] == "erp_implementation"
    assert row["response_due_at"] is None or row["first_response_at"] is None
    by_cat = client.get(f"{ADM}/enquiries?category=erp_implementation", headers=sa).json()
    assert [r["reference_number"] for r in by_cat["data"]] == [proj] and by_cat["meta"][
        "total"
    ] == 1
    assert client.get(f"{ADM}/enquiries?project_group=it", headers=sa).json()["meta"]["total"] == 1
    assert (
        client.get(f"{ADM}/enquiries?project_group=non_it", headers=sa).json()["meta"]["total"] == 0
    )
    assert client.get(f"{ADM}/enquiries?assigned_any=true", headers=sa).json()["meta"]["total"] == 1
    assert client.get(f"{ADM}/enquiries?category=nonsense", headers=sa).status_code == 422
    strategic = client.post(f"{PUB}/strategic", json=factories.strategic()).json()["data"][
        "reference_number"
    ]
    strategic_rows = client.get(f"{ADM}/enquiries?discussion_type=merger", headers=sa).json()
    assert [r["reference_number"] for r in strategic_rows["data"]] == [strategic]
    assert client.get(f"{ADM}/enquiries?discussion_type=merger", headers=bdm).json()["data"] == []
    assert client.get(f"{ADM}/enquiries?discussion_type=unknown", headers=sa).status_code == 422
    workload = client.get(f"{ADM}/workload", headers=sa).json()["data"]
    assert workload["totals"]["open_enquiries"] == sum(
        row["open_enquiries"] for row in workload["rows"]
    )
    assert workload["totals"]["open_enquiries"] >= 2
    assert (
        client.get(f"{ADM}/workload", headers=bdm).json()["data"]["totals"]["open_enquiries"] == 2
    )
    assert client.get(f"{ADM}/enquiries/{ids[proj]}/documents", headers=bdm).status_code == 200
    future = (utcnow() + timedelta(days=1)).isoformat()
    after = client.get(f"{ADM}/enquiries", params={"updated_from": future}, headers=sa).json()
    assert after["data"] == [] and after["meta"]["total"] == 0
    asc = client.get(f"{ADM}/enquiries?sort=created_at&page_size=100", headers=sa).json()["data"]
    desc = client.get(f"{ADM}/enquiries?sort=-created_at&page_size=100", headers=sa).json()["data"]
    assert [r["id"] for r in asc] == [r["id"] for r in reversed(desc)]
    assert client.get(f"{ADM}/enquiries?sort=contact_email", headers=sa).status_code == 422
    csv = client.get(f"{ADM}/reports/enquiries.csv?category=erp_implementation", headers=bdm)
    assert csv.status_code == 200 and proj in csv.text and csv.text.count("CS-ENQ") == 1
    assert sa_user.id != bdm_user.id


def test_followup_kinds_owner_update_and_cancel(
    client: TestClient, db: Session, settings: Settings
) -> None:
    _, sa = _h(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    bdm_user, bdm = _h(client, db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
    reviewer_user, _ = _h(client, db, settings, StaffRole.PARTNER_REVIEWER)
    ref = client.post(f"{PUB}/contact", json=factories.contact()).json()["data"]["reference_number"]
    eid = _ids(client, sa)[ref]
    fu = f"{ADM}/enquiries/{eid}/follow-ups"

    note = client.post(fu, headers=bdm, json={"note": "Internal view", "kind": "note"})
    assert note.status_code == 201 and note.json()["data"]["kind"] == "note"
    assert note.json()["data"]["author_name"] == "Staff Member"
    row = db.execute(select(Enquiry).where(Enquiry.id == eid)).scalar_one()
    assert row.first_response_at is None  # an internal note is not a response
    bad_due = client.post(
        fu, headers=bdm, json={"note": "x", "kind": "note", "due_at": utcnow().isoformat()}
    )
    assert bad_due.status_code == 422 and bad_due.json()["error"]["code"] == "DUE_DATE_NOT_ALLOWED"
    assert client.post(fu, headers=bdm, json={"note": "x", "kind": "gossip"}).status_code == 422
    invalid_owner = client.post(
        fu, headers=bdm, json={"note": "x", "assignee_id": str(reviewer_user.id)}
    )
    assert (
        invalid_owner.status_code == 422
        and invalid_owner.json()["error"]["code"] == "INVALID_OWNER"
    )

    comm = client.post(
        fu, headers=bdm, json={"note": "Called the requester", "kind": "communication"}
    )
    db.refresh(row)
    assert comm.status_code == 201 and row.first_response_at is not None

    due = (utcnow() + timedelta(days=2)).replace(microsecond=0)
    task = client.post(
        fu,
        headers=bdm,
        json={"note": "Send proposal", "due_at": due.isoformat(), "assignee_id": str(bdm_user.id)},
    ).json()["data"]
    assert task["status"] == "open" and task["assignee_name"] == "Staff Member"
    later = (due + timedelta(days=3)).replace(microsecond=0)
    upd = client.patch(f"{fu}/{task['id']}", headers=bdm, json={"due_at": later.isoformat()})
    assert upd.status_code == 200 and upd.json()["data"]["due_at"].startswith(
        later.isoformat()[:19]
    )
    db.refresh(row)
    assert (
        row.next_follow_up_at is not None and row.next_follow_up_at.replace(microsecond=0) == later
    )
    cleared = client.patch(f"{fu}/{task['id']}", headers=bdm, json={"assignee_id": None})
    assert cleared.json()["data"]["assignee_id"] is None
    assert (
        client.patch(
            f"{fu}/{task['id']}", headers=bdm, json={"note": "Send revised proposal"}
        ).status_code
        == 200
    )
    assert (
        client.patch(f"{fu}/{task['id']}", headers=bdm, json={"status": "completed"}).status_code
        == 422
    )

    cancelled = client.post(f"{fu}/{task['id']}/cancel", headers=bdm)
    assert cancelled.status_code == 200 and cancelled.json()["data"]["status"] == "cancelled"
    db.refresh(row)
    assert row.next_follow_up_at is None  # cancelled work no longer schedules anything
    for blocked in (
        client.post(f"{fu}/{task['id']}/cancel", headers=bdm),
        client.patch(f"{fu}/{task['id']}", headers=bdm, json={"note": "again"}),
        client.post(f"{fu}/{task['id']}/complete", headers=bdm),
    ):
        assert blocked.status_code in (409, 200)
    again = client.patch(f"{fu}/{task['id']}", headers=bdm, json={"note": "again"})
    assert again.status_code == 409 and again.json()["error"]["code"] == "FOLLOWUP_CLOSED"
    detail = client.get(f"{ADM}/enquiries/{eid}", headers=bdm).json()["data"]
    assert {f["kind"] for f in detail["follow_ups"]} == {"note", "communication", "follow_up"}
    assert all("author_name" in f and "status" in f for f in detail["follow_ups"])


def test_global_followups_counts_filters_and_strategic_isolation(
    client: TestClient, db: Session, settings: Settings
) -> None:
    sa_user, sa = _h(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    _, bdm = _h(client, db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
    _, cms = _h(client, db, settings, StaffRole.CONTENT_ADMINISTRATOR)
    g = client.post(f"{PUB}/contact", json=factories.contact()).json()["data"]["reference_number"]
    s = client.post(f"{PUB}/strategic", json=factories.strategic()).json()["data"][
        "reference_number"
    ]
    ids = _ids(client, sa)
    past = (utcnow() - timedelta(days=1)).isoformat()
    soon = (utcnow() + timedelta(days=1)).isoformat()
    client.post(
        f"{ADM}/enquiries/{ids[g]}/follow-ups", headers=sa, json={"note": "late", "due_at": past}
    )
    client.post(
        f"{ADM}/enquiries/{ids[g]}/follow-ups", headers=sa, json={"note": "soon", "due_at": soon}
    )
    client.post(
        f"{ADM}/enquiries/{ids[s]}/follow-ups",
        headers=sa,
        json={"note": "SECRET-FU", "due_at": soon},
    )

    body = client.get(f"{ADM}/follow-ups?page_size=100", headers=sa).json()
    assert body["meta"]["total"] == 3 and body["meta"]["counts"]["overdue"] == 1
    assert {r["enquiry_reference"] for r in body["data"]} == {g, s}
    mine = client.get(f"{ADM}/follow-ups?mine=true", headers=sa).json()
    assert mine["meta"]["total"] == 3
    assert client.get(f"{ADM}/follow-ups?kind=note", headers=sa).json()["meta"]["total"] == 0
    desc = client.get(f"{ADM}/follow-ups?sort=-due_at", headers=sa).json()["data"]
    asc = client.get(f"{ADM}/follow-ups?sort=due_at", headers=sa).json()["data"]
    assert [r["id"] for r in asc] == [r["id"] for r in reversed(desc)]
    ranged = client.get(f"{ADM}/follow-ups", params={"due_to": utcnow().isoformat()}, headers=sa)
    assert ranged.json()["meta"]["total"] == 1

    other = client.get(f"{ADM}/follow-ups?page_size=100", headers=bdm)
    assert other.status_code == 200 and "SECRET-FU" not in other.text and s not in other.text
    assert other.json()["meta"]["total"] == 2 and other.json()["meta"]["counts"]["open"] == 2
    assert client.get(f"{ADM}/follow-ups", headers=cms).status_code == 403
    sid = ids[s]
    fid = next(r["id"] for r in body["data"] if r["enquiry_reference"] == s)
    assert (
        client.patch(
            f"{ADM}/enquiries/{sid}/follow-ups/{fid}", headers=bdm, json={"note": "x"}
        ).status_code
        == 404
    )
    assert (
        client.post(f"{ADM}/enquiries/{sid}/follow-ups/{fid}/cancel", headers=bdm).status_code
        == 404
    )
    assert client.get(f"{ADM}/enquiries/{sid}/activity", headers=bdm).status_code == 404
    assert sa_user.id


def test_enquiry_activity_has_actor_names_and_filters(
    client: TestClient, db: Session, settings: Settings
) -> None:
    _, sa = _h(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    bdm_user, bdm = _h(client, db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
    ref = client.post(f"{PUB}/contact", json=factories.contact()).json()["data"]["reference_number"]
    eid = _ids(client, sa)[ref]
    client.post(f"{ADM}/enquiries/{eid}/assign", headers=sa, json={"user_id": str(bdm_user.id)})
    client.patch(f"{ADM}/enquiries/{eid}", headers=bdm, json={"status": "in_progress"})
    log = client.get(f"{ADM}/enquiries/{eid}/activity", headers=bdm).json()
    actions = [a["action"] for a in log["data"]]
    assert "admin.enquiry_assigned" in actions and log["meta"]["total"] == len(actions)
    assigned = next(a for a in log["data"] if a["action"] == "admin.enquiry_assigned")
    assert assigned["actor_name"] == "Staff Member" and assigned["meta"]["owner"] == str(
        bdm_user.id
    )
    only = client.get(f"{ADM}/enquiries/{eid}/activity?action=assign", headers=bdm).json()["data"]
    assert only and all("assign" in a["action"] for a in only)
    assert (
        client.get(
            f"{ADM}/enquiries/{'0' * 8}-0000-0000-0000-{'0' * 12}/activity", headers=bdm
        ).status_code
        == 404
    )
