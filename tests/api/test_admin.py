"""Phase 3 admin tests. Written during the development-only cycle; NOT executed yet."""

import csv
import io
import re
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.auth.constants import StaffRole
from app.modules.enquiries.models import Activity
from tests import factories
from tests.fakes import RecordingEmail
from tests.helpers import make_staff, staff_headers

ADM = "/api/v1/admin"
PUB = "/api/v1/enquiries"


def seed(client: TestClient) -> dict[str, str]:
    refs = {}
    refs["general"] = client.post(f"{PUB}/contact", json=factories.contact()).json()["data"][
        "reference_number"
    ]
    refs["project"] = client.post(
        f"{PUB}/project", json=factories.project(company_name="Proj Co")
    ).json()["data"]["reference_number"]
    refs["partner"] = client.post(f"{PUB}/partner", json=factories.partner()).json()["data"][
        "reference_number"
    ]
    refs["strategic"] = client.post(
        f"{PUB}/strategic", json=factories.strategic(company_name="=cmd|' /C calc'!A0")
    ).json()["data"]["reference_number"]
    return refs


def staff(client: TestClient, db: Session, settings: Settings, role: StaffRole):  # type: ignore[no-untyped-def]
    user = make_staff(db, settings, role)
    return user, staff_headers(client, user)


def test_anonymous_and_wrong_roles_rejected(
    client: TestClient, db: Session, settings: Settings
) -> None:
    paths = [p for p in client.get("/openapi.json").json()["paths"] if p.startswith(ADM)]
    assert len(paths) >= 15
    for p in paths:
        url = re.sub(r"\{[^}]+\}", str(uuid.uuid4()), p)
        assert client.get(url).status_code in (401, 405), url
    _, rev = staff(client, db, settings, StaffRole.PARTNER_REVIEWER)
    assert client.get(f"{ADM}/overview", headers=rev).status_code == 403
    assert client.get(f"{ADM}/enquiries", headers=rev).status_code == 403


def test_bdm_cannot_see_strategic_or_financial_data(
    client: TestClient, db: Session, settings: Settings
) -> None:
    refs = seed(client)
    _, bdm = staff(client, db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
    _, admin = staff(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    rows = client.get(f"{ADM}/enquiries", headers=bdm).json()["data"]
    assert {r["enquiry_type"] for r in rows} == {"general", "project", "partner"}
    all_rows = client.get(f"{ADM}/enquiries", headers=admin).json()
    assert {r["enquiry_type"] for r in all_rows["data"]} == {
        "general",
        "project",
        "partner",
        "strategic",
    }
    by_ref = {r["reference_number"]: r["id"] for r in all_rows["data"]}
    assert (
        client.get(f"{ADM}/enquiries/{by_ref[refs['strategic']]}", headers=bdm).status_code == 404
    )
    strat = client.get(f"{ADM}/enquiries/{by_ref[refs['strategic']]}", headers=admin).json()["data"]
    assert strat["details"]["access_classification"] == "confidential"
    p_bdm = client.get(f"{ADM}/enquiries/{by_ref[refs['partner']]}", headers=bdm).json()["data"][
        "details"
    ]
    p_adm = client.get(f"{ADM}/enquiries/{by_ref[refs['partner']]}", headers=admin).json()["data"][
        "details"
    ]
    assert p_bdm.get("turnover_range") is None and p_bdm.get("client_references") is None
    assert "turnover_range" in p_adm
    assert client.get(f"{ADM}/enquiries?type=strategic", headers=bdm).json()["data"] == []
    csv_bdm = client.get(f"{ADM}/reports/enquiries.csv", headers=bdm).text
    assert refs["strategic"] not in csv_bdm and refs["general"] in csv_bdm


def test_filters_search_pagination(client: TestClient, db: Session, settings: Settings) -> None:
    seed(client)
    _, admin = staff(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    r = client.get(f"{ADM}/enquiries?page_size=2&page=1", headers=admin).json()
    assert len(r["data"]) == 2 and r["meta"]["total"] == 4 and r["meta"]["pages"] == 2
    assert len(client.get(f"{ADM}/enquiries?type=project", headers=admin).json()["data"]) == 1
    assert len(client.get(f"{ADM}/enquiries?q=Proj Co", headers=admin).json()["data"]) == 1
    assert (
        client.get(f"{ADM}/enquiries?q=%25", headers=admin).json()["data"] == []
    )  # '%' is literal
    assert len(client.get(f"{ADM}/enquiries?unassigned=true", headers=admin).json()["data"]) == 4
    assert client.get(f"{ADM}/enquiries?page_size=1000", headers=admin).status_code == 422


def test_assignment_status_and_followups(
    client: TestClient, db: Session, settings: Settings
) -> None:
    refs = seed(client)
    bdm_user, bdm = staff(client, db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
    admin_user, admin = staff(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    rev_user, _ = staff(client, db, settings, StaffRole.PARTNER_REVIEWER)
    rows = client.get(f"{ADM}/enquiries", headers=admin).json()["data"]
    ids = {r["reference_number"]: r["id"] for r in rows}
    gid, sid = ids[refs["general"]], ids[refs["strategic"]]
    assert (
        client.post(
            f"{ADM}/enquiries/{gid}/assign", headers=bdm, json={"user_id": str(rev_user.id)}
        ).status_code
        == 422
    )
    ok = client.post(
        f"{ADM}/enquiries/{gid}/assign", headers=bdm, json={"user_id": str(bdm_user.id)}
    )
    assert ok.status_code == 200 and ok.json()["data"]["assigned_user_id"] == str(bdm_user.id)
    # strategic: only super administrators may own it
    assert (
        client.post(
            f"{ADM}/enquiries/{sid}/assign", headers=admin, json={"user_id": str(bdm_user.id)}
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"{ADM}/enquiries/{sid}/assign", headers=admin, json={"user_id": str(admin_user.id)}
        ).status_code
        == 200
    )
    upd = client.patch(
        f"{ADM}/enquiries/{gid}", headers=bdm, json={"status": "in_review", "priority": "high"}
    )
    assert upd.json()["data"]["status"] == "in_review" and upd.json()["data"]["priority"] == "high"
    assert (
        client.patch(f"{ADM}/enquiries/{gid}", headers=bdm, json={"status": "bogus"}).status_code
        == 422
    )
    due = "2030-01-01T10:00:00Z"
    f1 = client.post(
        f"{ADM}/enquiries/{gid}/follow-ups", headers=bdm, json={"note": "Call back", "due_at": due}
    )
    assert f1.status_code == 201
    detail = client.get(f"{ADM}/enquiries/{gid}", headers=bdm).json()["data"]
    assert (
        detail["enquiry"]["next_follow_up_at"].startswith("2030-01-01")
        and len(detail["follow_ups"]) == 1
    )
    client.post(f"{ADM}/enquiries/{gid}/follow-ups/{f1.json()['data']['id']}/complete", headers=bdm)
    assert (
        client.get(f"{ADM}/enquiries/{gid}", headers=bdm).json()["data"]["enquiry"][
            "next_follow_up_at"
        ]
        is None
    )
    assert (
        client.post(
            f"{ADM}/enquiries/{sid}/follow-ups", headers=bdm, json={"note": "x"}
        ).status_code
        == 404
    )
    actions = set(db.execute(select(Activity.action)).scalars())
    assert {
        "admin.enquiry_assigned",
        "admin.enquiry_updated",
        "admin.followup_added",
        "admin.followup_completed",
    } <= actions
    notes = [
        a.meta
        for a in db.execute(
            select(Activity).where(Activity.action == "admin.followup_added")
        ).scalars()
    ]
    assert "Call back" not in str(notes)  # note text is not copied into the audit trail


def test_csv_export_is_safe_and_audited(
    client: TestClient, db: Session, settings: Settings
) -> None:
    refs = seed(client)
    _, admin = staff(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    r = client.get(f"{ADM}/reports/enquiries.csv?type=strategic", headers=admin)
    assert (
        r.headers["content-type"].startswith("text/csv")
        and r.headers["cache-control"] == "private, no-store"
    )
    rows = list(csv.reader(io.StringIO(r.text)))
    assert rows[0][0] == "reference" and rows[1][0] == refs["strategic"]
    assert rows[1][rows[0].index("company")].startswith("'=")  # formula neutralised
    assert "TOP-SECRET-MARKER" not in r.text  # confidential text is never exported
    assert "admin.report_exported" in set(db.execute(select(Activity.action)).scalars())
    apps = client.get(f"{ADM}/reports/applications.csv", headers=admin)
    assert apps.status_code == 200 and apps.text.startswith("reference,organization")


def test_organizations_and_staff_management(
    client: TestClient, db: Session, settings: Settings
) -> None:
    email = RecordingEmail()
    del email
    _, bdm = staff(client, db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
    admin_user, admin = staff(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    orgs = client.get(f"{ADM}/organizations", headers=bdm)
    assert orgs.status_code == 200
    assert (
        client.post(
            f"{ADM}/organizations/{uuid.uuid4()}/status",
            headers=bdm,
            json={"status": "suspended", "reason": "x"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"{ADM}/organizations/{uuid.uuid4()}/status",
            headers=admin,
            json={"status": "bogus", "reason": "x"},
        ).status_code
        == 422
    )
    # staff users
    assert client.get(f"{ADM}/users", headers=bdm).status_code == 403
    inv = client.post(
        f"{ADM}/users",
        headers=admin,
        json={
            "email": "new.bdm@example.com",
            "full_name": "New BDM",
            "role": "business_development_manager",
        },
    )
    assert inv.status_code == 201 and inv.json()["data"]["status"] == "invited"
    assert (
        client.post(
            f"{ADM}/users",
            headers=admin,
            json={"email": "new.bdm@example.com", "full_name": "Dup", "role": "partner_reviewer"},
        ).status_code
        == 409
    )
    new_id = inv.json()["data"]["id"]
    assert (
        client.post(f"{ADM}/users/{new_id}/activate", headers=admin).status_code == 409
    )  # not accepted yet
    # safety rails
    assert client.post(f"{ADM}/users/{admin_user.id}/deactivate", headers=admin).status_code == 409
    assert (
        client.post(
            f"{ADM}/users/{admin_user.id}/role", headers=admin, json={"role": "partner_reviewer"}
        ).status_code
        == 409
    )
    other = make_staff(db, settings, StaffRole.PARTNER_REVIEWER)
    other_h = staff_headers(client, other)
    me = client.get("/api/v1/auth/me", headers=other_h)
    assert me.status_code == 200 and me.json()["data"]["account_status"] == "active"
    assert client.post(f"{ADM}/users/{other.id}/deactivate", headers=admin).status_code == 200
    assert client.get("/api/v1/auth/me", headers=other_h).status_code == 401  # sessions revoked


def test_audit_log_super_admin_only(client: TestClient, db: Session, settings: Settings) -> None:
    seed(client)
    _, bdm = staff(client, db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
    _, admin = staff(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    assert client.get(f"{ADM}/audit", headers=bdm).status_code == 403
    r = client.get(f"{ADM}/audit?record_type=enquiry&action=submitted", headers=admin).json()
    assert r["meta"]["total"] == 4 and all(a["action"] == "enquiry.submitted" for a in r["data"])
    ov = client.get(f"{ADM}/overview", headers=admin).json()["data"]
    assert ov["unassigned_enquiries"] == 4 and "recent_activity" in ov and "applications" in ov
    assert client.get(f"{ADM}/overview", headers=bdm).json()["data"].get("applications") is None
