"""Independent review tests for work inherited from the earlier agent (audit, workload, document
history, reports, scheduled publication, templates, field metadata, typed detail responses)."""

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.admin import maintenance
from app.modules.auth.constants import StaffRole
from app.modules.content.models import ContentItem
from tests import factories
from tests.fakes import RecordingEmail
from tests.helpers import bearer, login, make_staff, onboard_partner, submitted_application

ADM = "/api/v1/admin"
AC = "/api/v1/admin/content"


def _h(
    client: TestClient, db: Session, settings: Settings, role: StaffRole
) -> tuple[Any, dict[str, str]]:
    user = make_staff(db, settings, role)
    return user, bearer(login(client, user.email)["access_token"])


def test_audit_detail_actions_and_csv_are_super_admin_only_and_safe(
    client: TestClient, db: Session, settings: Settings
) -> None:
    _, sa = _h(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    _, bdm = _h(client, db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
    client.post(
        "/api/v1/enquiries/strategic", json=factories.strategic(company_name="=HYPERLINK(1)")
    )
    rows = client.get(f"{ADM}/audit?page_size=100", headers=sa).json()["data"]
    one = rows[0]
    got = client.get(f"{ADM}/audit/{one['id']}", headers=sa)
    assert got.status_code == 200 and got.json()["data"]["id"] == one["id"]
    flagged = next(r for r in rows if r["is_strategic"])
    assert (
        client.get(f"{ADM}/audit/{flagged['id']}", headers=sa).json()["data"]["is_strategic"]
        is True
    )
    assert (
        client.get(f"{ADM}/audit/00000000-0000-0000-0000-000000000000", headers=sa).status_code
        == 404
    )
    assert client.get(f"{ADM}/audit/not-a-uuid", headers=sa).status_code == 422
    actions = client.get(f"{ADM}/audit/actions", headers=sa).json()["data"]
    assert actions == sorted(set(actions)) and len(actions) >= 2
    csv = client.get(f"{ADM}/audit.csv", headers=sa)
    assert csv.status_code == 200 and csv.headers["content-type"].startswith("text/csv")
    assert (
        "attachment" in csv.headers["content-disposition"]
        and csv.headers["cache-control"] == "private, no-store"
    )
    assert len(csv.text.strip().splitlines()) - 1 == len(
        rows
    )  # one line per event, plus the header
    assert "\n=" not in csv.text and ",=" not in csv.text  # no formula can start a cell
    for url in (f"{ADM}/audit/{one['id']}", f"{ADM}/audit/actions", f"{ADM}/audit.csv"):
        assert client.get(url, headers=bdm).status_code == 403
        assert client.get(url).status_code == 401


def test_workload_counts_match_the_data_and_hide_strategic_from_bdm(
    client: TestClient, db: Session, settings: Settings
) -> None:
    _, sa = _h(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    bdm_user, bdm = _h(client, db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
    _, cms = _h(client, db, settings, StaffRole.CONTENT_ADMINISTRATOR)
    for _ in range(2):
        client.post("/api/v1/enquiries/contact", json=factories.contact())
    client.post("/api/v1/enquiries/strategic", json=factories.strategic())
    ids = [r["id"] for r in client.get(f"{ADM}/enquiries?type=general", headers=sa).json()["data"]]
    client.post(f"{ADM}/enquiries/{ids[0]}/assign", headers=sa, json={"user_id": str(bdm_user.id)})
    sid = client.get(f"{ADM}/enquiries?type=strategic", headers=sa).json()["data"][0]["id"]

    as_sa = client.get(f"{ADM}/workload", headers=sa).json()["data"]
    as_bdm = client.get(f"{ADM}/workload", headers=bdm).json()["data"]
    assert (
        as_sa["totals"]["open_enquiries"] == 3 and as_bdm["totals"]["open_enquiries"] == 2
    )  # strategic excluded
    assert sum(r["open_enquiries"] for r in as_sa["rows"]) == as_sa["totals"]["open_enquiries"]
    mine = next(r for r in as_bdm["rows"] if r["assignee_id"] == str(bdm_user.id))
    assert mine["open_enquiries"] == 1 and mine["assignee_name"] == "Staff Member"
    assert any(r["assignee_id"] is None for r in as_bdm["rows"])  # unassigned bucket
    assert sid not in str(as_bdm)
    assert client.get(f"{ADM}/workload", headers=cms).status_code == 403
    assert client.get(f"{ADM}/workload").status_code == 401


def test_document_history_is_scoped_to_assigned_organisations(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    _, sa = _h(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    reviewer, rev = _h(client, db, settings, StaffRole.PARTNER_REVIEWER)
    _, other = _h(client, db, settings, StaffRole.PARTNER_REVIEWER)
    _, bdm = _h(client, db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
    p = onboard_partner(client, db, settings, email, org_name="Hist Ltd")
    app_id = submitted_application(client, p)
    docs = client.get("/api/v1/partner/documents", headers=p.headers).json()["data"]
    doc_id = docs[0]["id"]
    client.post(
        f"/api/v1/reviewer/applications/{app_id}/assign",
        headers=sa,
        json={"reviewer_id": str(reviewer.id)},
    )

    url = f"{ADM}/documents/{doc_id}/history"
    ok = client.get(url, headers=rev)
    assert ok.status_code == 200 and ok.json()["meta"]["total"] >= 1
    row = ok.json()["data"][0]
    assert "storage_key" not in str(row) and "checksum" not in str(row)
    assert client.get(url, headers=sa).status_code == 200
    assert client.get(url, headers=other).status_code == 404  # reviewer without the assignment
    assert client.get(url, headers=bdm).status_code == 403
    assert client.get(url, headers=p.headers).status_code == 403
    assert (
        client.get(
            f"{ADM}/documents/00000000-0000-0000-0000-000000000000/history", headers=sa
        ).status_code
        == 404
    )


def test_reports_exclude_strategic_follow_ups_for_bdm_and_deny_other_roles(
    client: TestClient, db: Session, settings: Settings
) -> None:
    _, sa = _h(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    _, bdm = _h(client, db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
    _, rev = _h(client, db, settings, StaffRole.PARTNER_REVIEWER)
    client.post("/api/v1/enquiries/contact", json=factories.contact())
    client.post("/api/v1/enquiries/strategic", json=factories.strategic())
    gid = client.get(f"{ADM}/enquiries?type=general", headers=sa).json()["data"][0]["id"]
    sid = client.get(f"{ADM}/enquiries?type=strategic", headers=sa).json()["data"][0]["id"]
    client.post(
        f"{ADM}/enquiries/{gid}/follow-ups", headers=sa, json={"note": "a", "kind": "communication"}
    )
    client.post(
        f"{ADM}/enquiries/{sid}/follow-ups", headers=sa, json={"note": "b", "kind": "communication"}
    )
    full = client.get(f"{ADM}/reports/follow-ups", headers=sa).json()["data"]
    limited = client.get(f"{ADM}/reports/follow-ups", headers=bdm).json()["data"]
    assert full["total"] == 2 and limited["total"] == 1
    assert (
        sum(
            full["by_kind"].values()
            if isinstance(full["by_kind"], dict)
            else [x["count"] for x in full["by_kind"]]
        )
        == 2
    )
    for path in ("follow-ups", "document-review", "communications", "kpis"):
        assert client.get(f"{ADM}/reports/{path}", headers=rev).status_code == 403
        assert client.get(f"{ADM}/reports/{path}").status_code == 401
    future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    none = client.get(
        f"{ADM}/reports/follow-ups", params={"created_from": future}, headers=sa
    ).json()["data"]
    assert none["total"] == 0
    comms = client.get(f"{ADM}/reports/communications", headers=bdm)
    assert comms.status_code in (200, 403)
    if comms.status_code == 200:
        assert "TOP-SECRET" not in comms.text


def test_scheduled_publication_negative_cases(
    client: TestClient, db: Session, settings: Settings
) -> None:
    _, ca = _h(client, db, settings, StaffRole.CONTENT_ADMINISTRATOR)
    _, sa = _h(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    _, bdm = _h(client, db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
    made = client.post(
        AC,
        headers=ca,
        json={"slug": "later", "content_type": "page", "title": "Later", "body": "b"},
    )
    item_id = made.json()["data"]["id"]
    when = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    draft = client.post(f"{AC}/{item_id}/schedule", headers=ca, json={"publish_at": when})
    assert draft.status_code == 409  # only approved content
    client.post(f"{AC}/{item_id}/submit", headers=ca, json={})
    client.post(f"{AC}/{item_id}/approve", headers=sa, json={"note": "ok"})
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    bad = client.post(f"{AC}/{item_id}/schedule", headers=ca, json={"publish_at": past})
    assert bad.status_code == 422  # rejected before it reaches the service
    assert (
        client.post(f"{AC}/{item_id}/schedule", headers=bdm, json={"publish_at": when}).status_code
        == 403
    )
    assert client.post(f"{AC}/{item_id}/schedule", json={"publish_at": when}).status_code == 401
    ok = client.post(f"{AC}/{item_id}/schedule", headers=ca, json={"publish_at": when})
    assert ok.status_code == 200
    assert maintenance.publish_scheduled_content(db) == 0  # not due yet
    assert client.get("/api/v1/content/later").status_code == 404
    # the schedule disappears if the content is reopened (no surprise publication)
    client.post(f"{AC}/{item_id}/reopen", headers=ca, json={})
    row = db.get(ContentItem, item_id)
    assert row is not None
    row.scheduled_publish_at = datetime.now(UTC) - timedelta(seconds=1)
    db.flush()
    assert maintenance.publish_scheduled_content(db) == 0  # a draft is never auto-published
    assert client.get("/api/v1/content/later").status_code == 404


def test_field_metadata_templates_and_typed_details_have_stable_contracts(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    _, sa = _h(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    _, bdm = _h(client, db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
    p = onboard_partner(client, db, settings, email, org_name="Meta Ltd")
    meta = client.get("/api/v1/partner/organization/editable-fields", headers=p.headers).json()[
        "data"
    ]
    names = {m["name"] for m in meta}
    assert {"legal_name", "website", "country"} <= names and "expected_version" not in names
    legal = next(m for m in meta if m["name"] == "legal_name")
    assert legal["nullable"] is False and legal["null_clears"] is False
    assert client.get("/api/v1/partner/organization/editable-fields", headers=sa).status_code == 403
    assert client.get("/api/v1/partner/organization/editable-fields").status_code == 401

    ph = client.get(f"{ADM}/notification-templates/placeholders", headers=sa)
    assert ph.status_code == 200
    assert client.get(f"{ADM}/notification-templates/placeholders", headers=bdm).status_code == 403
    secret_words = ("password", "token", "secret", "hash")
    assert not any(w in ph.text.lower() for w in secret_words)

    detail_sa = client.get(f"{ADM}/organizations/{p.organization_id}", headers=sa).json()["data"]
    detail_bdm = client.get(f"{ADM}/organizations/{p.organization_id}", headers=bdm).json()["data"]
    assert set(detail_sa) == {"profile", "applications"} == set(detail_bdm)
    assert detail_bdm["profile"]["annual_turnover_inr_crore"] is None  # financial: super admin only
    assert detail_bdm["profile"]["client_references"] is None
    overview = client.get(f"{ADM}/overview", headers=sa).json()["data"]
    assert {"enquiries", "unassigned_enquiries", "overdue_follow_ups"} <= set(overview)


def test_discussion_type_filter_is_validated_and_confidential(
    client: TestClient, db: Session, settings: Settings
) -> None:
    _, sa = _h(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    _, bdm = _h(client, db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
    client.post("/api/v1/enquiries/strategic", json=factories.strategic(discussion_type="merger"))
    merger = client.get(f"{ADM}/enquiries?discussion_type=merger", headers=sa).json()
    assert merger["meta"]["total"] == 1 and merger["data"][0]["category"] == "merger"
    other = client.get(f"{ADM}/enquiries?discussion_type=integration", headers=sa).json()
    assert other["meta"]["total"] == 0
    assert client.get(f"{ADM}/enquiries?discussion_type=bogus", headers=sa).status_code == 422
    assert client.get(f"{ADM}/enquiries?discussion_type=merger", headers=bdm).json()["data"] == []
