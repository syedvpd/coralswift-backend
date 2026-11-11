"""Owner decisions D9/D15/D27/D42/D45 plus the last coding gaps: staff team list, notification
description/link, information-request due date, KPI filters and application turnaround."""

from datetime import datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.common.utilities import utcnow
from app.core.config import Settings
from app.modules.applications.constants import PARTNER_LABELS, PortalStatus
from app.modules.applications.models import PortalApplication
from app.modules.auth.constants import StaffRole
from tests import factories
from tests.fakes import RecordingEmail
from tests.helpers import bearer, login, make_staff, onboard_partner, submitted_application

R = "/api/v1/reviewer"
P = "/api/v1/partner"
ADM = "/api/v1/admin"


def _staff(client: TestClient, db: Session, settings: Settings, role: StaffRole):  # type: ignore[no-untyped-def]
    user = make_staff(db, settings, role)
    return user, bearer(login(client, user.email)["access_token"])


def _iso(moment: datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


def _assign_org_to_bdm(client: TestClient, sa: dict[str, str], org_id: str, bdm_id: Any) -> None:
    res = client.post(
        f"{ADM}/organizations/{org_id}/bdm-assignments", headers=sa, json={"user_id": str(bdm_id)}
    )
    assert res.status_code == 201, res.text


def test_bdm_read_only_access_limited_to_assigned_organisations(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    _, sa = _staff(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    bdm_user, bdm = _staff(client, db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
    mine = onboard_partner(client, db, settings, email)
    other = onboard_partner(client, db, settings, email)
    _assign_org_to_bdm(client, sa, mine.organization_id, bdm_user.id)

    def make(org: str) -> tuple[str, str, str]:
        proj = client.post(
            f"{R}/projects", headers=sa, json={"organization_id": org, "title": "P"}
        ).json()["data"]["id"]
        item = client.post(
            f"{R}/collaboration",
            headers=sa,
            json={"organization_id": org, "kind": "discussion", "title": "D"},
        ).json()["data"]["id"]
        rec = client.post(f"{R}/onboarding", headers=sa, json={"organization_id": org}).json()[
            "data"
        ]["id"]
        return str(proj), str(item), str(rec)

    p1, i1, r1 = make(mine.organization_id)
    p2, i2, r2 = make(other.organization_id)
    client.post(
        f"{R}/partner-messages",
        headers=sa,
        json={"organization_id": mine.organization_id, "subject": "S", "body": "B"},
    )
    mine_org, other_org = mine.organization_id, other.organization_id

    assert [p["id"] for p in client.get(f"{R}/projects", headers=bdm).json()["data"]] == [p1]
    assert client.get(f"{R}/projects/{p1}", headers=bdm).status_code == 200
    assert client.get(f"{R}/projects/{p2}", headers=bdm).status_code == 404
    assert [i["id"] for i in client.get(f"{R}/collaboration", headers=bdm).json()["data"]] == [i1]
    assert client.get(f"{R}/collaboration/{i2}", headers=bdm).status_code == 404
    assert [r["id"] for r in client.get(f"{R}/onboarding", headers=bdm).json()["data"]] == [r1]
    assert client.get(f"{R}/onboarding/{r2}", headers=bdm).status_code == 404
    assert len(client.get(f"{R}/partner-messages", headers=bdm).json()["data"]) == 1
    team_url = f"{R}/organizations/{mine_org}/team"
    assert client.get(team_url, headers=bdm).status_code == 200
    assert client.get(f"{R}/organizations/{other_org}/team", headers=bdm).status_code == 404

    msg = {"organization_id": mine_org, "subject": "a", "body": "b"}
    writes = [
        client.post(f"{R}/projects", headers=bdm, json={"organization_id": mine_org, "title": "x"}),
        client.patch(f"{R}/projects/{p1}", headers=bdm, json={"title": "y"}),
        client.post(f"{R}/projects/{p1}/share", headers=bdm),
        client.post(f"{R}/collaboration/{i1}/share", headers=bdm),
        client.post(f"{R}/collaboration/{i1}/reply", headers=bdm, json={"body": "x"}),
        client.post(f"{R}/partner-messages", headers=bdm, json=msg),
        client.post(f"{R}/onboarding/{r1}/tasks", headers=bdm, json={"name": "T"}),
        client.post(f"{R}/onboarding/{r1}/complete", headers=bdm),
        client.post(f"{R}/organizations/{mine_org}/performance", headers=bdm, json={}),
        client.get(f"{R}/organizations/{mine_org}/performance", headers=bdm),
    ]
    assert [w.status_code for w in writes] == [403] * len(writes)
    invite = {"email": "x@example.com", "full_name": "X Y"}
    assert client.post(f"{P}/team/invitations", headers=bdm, json=invite).status_code == 403
    assert client.get(f"{P}/team", headers=bdm).status_code == 403
    assert client.get(f"{R}/projects/{p1}", headers=sa).json()["data"]["title"] == "P"


def test_staff_team_list_for_admins_and_reviewer_scope(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    _, sa = _staff(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    reviewer, rev = _staff(client, db, settings, StaffRole.PARTNER_REVIEWER)
    _, content = _staff(client, db, settings, StaffRole.CONTENT_ADMINISTRATOR)
    a = onboard_partner(client, db, settings, email)
    b = onboard_partner(client, db, settings, email)
    invitee = {"email": "invitee@example.com", "full_name": "Invited Person"}
    client.post(f"{P}/team/invitations", headers=a.headers, json=invitee)
    url_a = f"{R}/organizations/{a.organization_id}/team"
    team = client.get(url_a, headers=sa).json()
    assert team["meta"]["total"] == 2
    assert {m["invitation_pending"] for m in team["data"]} == {True, False}
    app_id = submitted_application(client, a)
    assign = {"reviewer_id": str(reviewer.id)}
    client.post(f"{R}/applications/{app_id}/assign", headers=sa, json=assign)
    assert client.get(url_a, headers=rev).status_code == 200
    assert client.get(f"{R}/organizations/{b.organization_id}/team", headers=rev).status_code == 404
    assert client.get(url_a, headers=content).status_code == 403
    assert client.get(url_a).status_code == 401


def test_information_request_due_date_and_decision_explanation(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    sa_user, sa = _staff(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    p = onboard_partner(client, db, settings, email)
    app_id = submitted_application(client, p)
    client.post(
        f"{R}/applications/{app_id}/assign", headers=sa, json={"reviewer_id": str(sa_user.id)}
    )
    past = (utcnow() - timedelta(days=2)).date().isoformat()
    req = client.post(
        f"{R}/applications/{app_id}/information-requests",
        headers=sa,
        json={"body": "Please send the latest accounts", "due_date": past},
    )
    assert req.status_code == 201 and req.json()["data"]["due_date"] == past
    msgs = client.get(f"{P}/applications/{app_id}/messages", headers=p.headers).json()["data"]
    assert msgs[0]["due_date"] == past and msgs[0]["is_overdue"] is True
    app = client.get(f"{P}/applications/{app_id}", headers=p.headers).json()["data"]
    assert app["next_information_due"] == past and app["decision_explanation"] is None
    bad = client.post(
        f"{R}/applications/{app_id}/information-requests",
        headers=sa,
        json={"body": "x", "due_date": "not-a-date"},
    )
    assert bad.status_code == 422

    # D27: decision plus a reviewer-written partner-safe note; the internal reason stays hidden
    q = onboard_partner(client, db, settings, email)
    decided_id = submitted_application(client, q)
    client.post(
        f"{R}/applications/{decided_id}/assign", headers=sa, json={"reviewer_id": str(sa_user.id)}
    )
    rejected = client.post(
        f"{R}/applications/{decided_id}/transition",
        headers=sa,
        json={
            "to_status": "rejected",
            "reason": "INTERNAL: weak references",
            "partner_note": "We cannot progress this application now.",
        },
    )
    assert rejected.status_code == 200, rejected.text
    decided = client.get(f"{P}/applications/{decided_id}", headers=q.headers).json()["data"]
    assert decided["decision_explanation"] == "We cannot progress this application now."
    assert decided["decided_at"] and "INTERNAL" not in str(decided)


def test_pilot_onboarding_label_is_approved_pilot() -> None:
    assert PARTNER_LABELS[PortalStatus.PILOT_ONBOARDING] == "Approved - pilot"


def test_notification_description_related_record_and_link(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    p = onboard_partner(client, db, settings, email)
    app_id = submitted_application(client, p)
    ref = client.get(f"{P}/applications/{app_id}", headers=p.headers).json()["data"]["reference"]
    rows = client.get(f"{P}/notifications", headers=p.headers).json()
    sub = next(n for n in rows["data"] if n["template"] == "application_submitted")
    assert sub["description"] and sub["related_record"] == {"type": "application", "reference": ref}
    assert sub["link"] == f"/applications?reference={ref}"
    assert "@" not in sub["description"]


def test_kpi_filters_by_assignee_category_and_dates(
    client: TestClient, db: Session, settings: Settings
) -> None:
    _, sa = _staff(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    bdm_user, bdm = _staff(client, db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
    other_user, _ = _staff(client, db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
    refs = []
    for category in ("erp_implementation", "data_entry"):
        r = client.post(
            "/api/v1/enquiries/project", json=factories.project(project_category=category)
        )
        assert r.status_code == 201, r.text
        refs.append(r.json()["data"]["reference_number"])
    general = client.post("/api/v1/enquiries/contact", json=factories.contact()).json()["data"]
    rows = {
        r["reference_number"]: r["id"]
        for r in client.get(f"{ADM}/enquiries?page_size=100", headers=sa).json()["data"]
    }
    for ref, uid in ((refs[0], bdm_user.id), (general["reference_number"], other_user.id)):
        res = client.post(
            f"{ADM}/enquiries/{rows[ref]}/assign", headers=sa, json={"user_id": str(uid)}
        )
        assert res.status_code == 200, res.text

    def total(query: str = "", headers: dict[str, str] | None = None) -> int:
        out = client.get(f"{ADM}/reports/kpis{query}", headers=headers or sa).json()["data"]
        return sum(r["count"] for r in out["enquiries_by_type_and_status"])

    everything = total()
    assert everything >= 3
    assert total(f"?assignee_id={bdm_user.id}") == 1
    assert total(f"?assignee_id={other_user.id}") == 1
    assert total("?category=erp_implementation") == 1
    assert total("?category=data_entry") == 1
    assert total(f"?assignee_id={bdm_user.id}&category=data_entry") == 0
    future = _iso(utcnow() + timedelta(days=1))
    assert total(f"?created_from={future}") == 0
    assert total(f"?created_to={future}") == everything
    assert client.get(f"{ADM}/reports/kpis?category=nonsense", headers=sa).status_code == 422
    assert total(f"?assignee_id={bdm_user.id}", bdm) == 1


def test_application_turnaround_and_onboarding_duration_metrics(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    _, sa = _staff(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    _, bdm = _staff(client, db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
    now = utcnow()
    for hours in (10, 30):
        p = onboard_partner(client, db, settings, email)
        app_id = submitted_application(client, p)
        db.execute(
            update(PortalApplication)
            .where(PortalApplication.id == app_id)
            .values(
                submitted_at=now - timedelta(hours=hours + 1),
                decided_at=now - timedelta(hours=1),
            )
        )
    db.commit()
    start = _iso(now - timedelta(hours=40))
    both = client.get(f"{ADM}/reports/kpis?created_from={start}", headers=sa).json()["data"]
    assert both["applications_decided"] >= 2
    only_30h = client.get(
        f"{ADM}/reports/kpis?created_from={start}&created_to={_iso(now - timedelta(hours=20))}",
        headers=sa,
    ).json()["data"]
    assert only_30h["applications_decided"] == 1
    assert only_30h["application_decision_turnaround_hours_avg"] == 30.0
    only_10h = client.get(
        f"{ADM}/reports/kpis?created_from={_iso(now - timedelta(hours=20))}", headers=sa
    ).json()["data"]
    assert only_10h["applications_decided"] == 1
    assert only_10h["application_decision_turnaround_hours_avg"] == 10.0
    assert (
        client.get(f"{ADM}/reports/kpis", headers=bdm).json()["data"]["applications_decided"]
        is None
    )


def test_privacy_sla_is_configurable_and_never_claims_legal_compliance(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    _, sa = _staff(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    p = onboard_partner(client, db, settings, email)
    made = client.post(f"{P}/privacy-requests", headers=p.headers, json={"kind": "access"})
    assert made.status_code == 201
    row = client.get(f"{ADM}/privacy-requests", headers=sa).json()["data"][0]
    created0 = datetime.fromisoformat(row["created_at"])
    default_due = datetime.fromisoformat(row["completion_due_at"]) - created0
    assert default_due == timedelta(days=30) and row["is_overdue"] is False  # provisional default
    put = client.put(f"{ADM}/settings/privacy.completion_days", headers=sa, json={"value": "14"})
    assert put.status_code == 200
    try:
        row = client.get(f"{ADM}/privacy-requests", headers=sa).json()["data"][0]
        created = datetime.fromisoformat(row["created_at"])
        assert datetime.fromisoformat(row["completion_due_at"]) - created == timedelta(days=14)
        assert row["is_overdue"] is False
        bad = client.put(f"{ADM}/settings/privacy.completion_days", headers=sa, json={"value": "0"})
        assert bad.status_code == 422
    finally:
        client.delete(f"{ADM}/settings/privacy.completion_days", headers=sa)
