"""Gap closure: pagination meta on every list, user/organization list contract, partner inbox."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.common.utilities import utcnow
from app.core.config import Settings
from app.modules.auth.constants import StaffRole
from tests import factories
from tests.fakes import RecordingEmail
from tests.helpers import bearer, login, make_staff, onboard_partner

ADM = "/api/v1/admin"
META_KEYS = {"page", "page_size", "total", "pages"}
# Lists that are intentionally complete (small, fixed reference data), not paginated.
UNPAGINATED = {
    "/api/v1/admin/notification-templates",  # one row per template key
    "/api/v1/catalog/project-categories",
    "/api/v1/content/sitemap",
    "/api/v1/partner/applications",  # a partner has at most a handful (one open at a time)
    "/api/v1/partner/enquiries",  # capped at 50, own submissions only
    "/api/v1/partner/organization/change-requests",
    "/api/v1/partner/organization/history",
    "/api/v1/partner/documents",
    "/api/v1/admin/assignees",  # active staff only, a handful
    "/api/v1/auth/sessions",  # your own sessions
    "/api/v1/reviewer/transitions",  # the fixed rule table
    "/api/v1/admin/audit/actions",  # event catalogue
    "/api/v1/admin/notification-templates/placeholders",  # fixed allow-list
    "/api/v1/partner/organization/editable-fields",  # field metadata
    "/api/v1/partner/performance/summary",  # one row per published indicator
    "/api/v1/partner/performance/scorecards",  # one group per published period
    "/api/v1/partner/onboarding",  # a single record, not a list
    "/api/v1/admin/onboarding-template",  # one editable task list
}


def _h(client: TestClient, db: Session, settings: Settings, role: StaffRole) -> dict[str, str]:
    return bearer(login(client, make_staff(db, settings, role).email)["access_token"])


def test_every_paginated_list_reports_page_total_and_pages(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    sa = _h(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    partner = onboard_partner(client, db, settings, email)
    client.post("/api/v1/enquiries/contact", json=factories.contact())
    paths = client.get("/openapi.json").json()["paths"]
    checked = []
    missing = []
    for path, ops in sorted(paths.items()):
        if "get" not in ops or "{" in path:
            continue
        for who, headers in (("staff", sa), ("partner", partner.headers)):
            r = client.get(path, headers=headers)
            if r.status_code != 200 or "application/json" not in r.headers.get("content-type", ""):
                continue
            body = r.json()
            if not isinstance(body.get("data"), list):
                continue
            checked.append((who, path))
            if path in UNPAGINATED:
                continue
            if not set(body.get("meta") or {}) >= META_KEYS:
                missing.append((who, path))
    assert len(checked) >= 15
    assert not missing, f"lists without page/page_size/total/pages: {missing}"


def test_staff_list_search_filter_sort_and_meta(
    client: TestClient, db: Session, settings: Settings
) -> None:
    sa = _h(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    make_staff(db, settings, StaffRole.PARTNER_REVIEWER, email="zed.reviewer@example.com")
    make_staff(db, settings, StaffRole.CONTENT_ADMINISTRATOR, email="amy.content@example.com")
    body = client.get(f"{ADM}/users?page_size=2", headers=sa).json()
    assert len(body["data"]) == 2 and body["meta"]["total"] >= 3 and body["meta"]["pages"] >= 2
    assert {"created_at", "updated_at"} <= set(body["data"][0])
    q = client.get(f"{ADM}/users?q=zed.reviewer", headers=sa).json()
    assert [u["email"] for u in q["data"]] == ["zed.reviewer@example.com"] and q["meta"][
        "total"
    ] == 1
    assert (
        client.get(f"{ADM}/users?role=content_administrator", headers=sa).json()["meta"]["total"]
        == 1
    )
    assert client.get(f"{ADM}/users?status=invited", headers=sa).json()["meta"]["total"] == 0
    by_name = client.get(f"{ADM}/users?sort=full_name&page_size=100", headers=sa).json()["data"]
    assert [u["full_name"] for u in by_name] == sorted(u["full_name"] for u in by_name)
    assert client.get(f"{ADM}/users?sort=password_hash", headers=sa).status_code == 422
    assert client.get(f"{ADM}/users?status=bogus", headers=sa).status_code == 422


def test_organization_list_filters_sort_and_contact(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    sa = _h(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    onboard_partner(client, db, settings, email, org_name="Zulu Systems Ltd")
    onboard_partner(client, db, settings, email, org_name="Alpha Systems Ltd")
    body = client.get(f"{ADM}/organizations?sort=legal_name", headers=sa).json()
    names = [o["legal_name"] for o in body["data"]]
    assert names == sorted(names) and body["meta"]["total"] == 2
    assert all("updated_at" in o and "primary_contact" in o for o in body["data"])
    assert client.get(f"{ADM}/organizations?q=zulu", headers=sa).json()["meta"]["total"] == 1
    assert (
        client.get(f"{ADM}/organizations?status=suspended", headers=sa).json()["meta"]["total"] == 0
    )
    assert client.get(f"{ADM}/organizations?status=weird", headers=sa).status_code == 422
    future = (utcnow() + timedelta(days=1)).isoformat()
    empty = client.get(f"{ADM}/organizations", params={"created_from": future}, headers=sa).json()
    assert empty["data"] == [] and empty["meta"]["total"] == 0
    assert client.get(f"{ADM}/organizations?sort=legal_name_desc", headers=sa).status_code == 422


def test_partner_inbox_read_state_isolation_and_unread_counts(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    a = onboard_partner(client, db, settings, email, org_name="Inbox A Ltd")
    b = onboard_partner(client, db, settings, email, org_name="Inbox B Ltd")
    for who in (a, b):  # two contact enquiries per partner create acknowledgement messages
        for _ in range(2):
            client.post(
                "/api/v1/enquiries/contact", json=factories.contact(business_email=who.email)
            )
    first = client.get("/api/v1/partner/notifications", headers=a.headers).json()
    assert first["meta"]["total"] == first["meta"]["unread"] == 2
    item = first["data"][0]
    assert set(item) == {
        "id",
        "template",
        "title",
        "category",
        "description",
        "related_record",
        "link",
        "related_reference",
        "delivery_status",
        "created_at",
        "read_at",
        "is_read",
    }
    # links are portal-relative paths only (never tokens or URLs with credentials)
    assert item["is_read"] is False and (item["link"] is None or item["link"].startswith("/"))
    foreign = client.get("/api/v1/partner/notifications", headers=b.headers).json()["data"][0]["id"]
    assert (
        client.post(f"/api/v1/partner/notifications/{foreign}/read", headers=a.headers).status_code
        == 404
    )
    done = client.post(f"/api/v1/partner/notifications/{item['id']}/read", headers=a.headers)
    assert done.status_code == 200 and done.json()["data"]["is_read"] is True
    after = client.get("/api/v1/partner/notifications", headers=a.headers).json()
    assert after["meta"]["unread"] == 1 and after["meta"]["total"] == 2
    only = client.get("/api/v1/partner/notifications?unread=true", headers=a.headers).json()
    assert only["meta"]["total"] == 1 and only["data"][0]["id"] != item["id"]
    assert (
        client.post("/api/v1/partner/notifications/read-all", headers=a.headers).json()["data"][
            "marked"
        ]
        == 1
    )
    assert (
        client.get("/api/v1/partner/notifications", headers=a.headers).json()["meta"]["unread"] == 0
    )
    assert (
        client.get("/api/v1/partner/notifications", headers=b.headers).json()["meta"]["unread"] == 2
    )
    assert client.get("/api/v1/partner/notifications").status_code == 401
    staff = _h(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    assert client.get("/api/v1/partner/notifications", headers=staff).status_code == 403


def test_content_list_sort_date_and_csv_cap(
    client: TestClient, db: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    cms = _h(client, db, settings, StaffRole.CONTENT_ADMINISTRATOR)
    sa = _h(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    body = {"content_type": "article", "title": "", "summary": "s", "body": "b", "category": "news"}
    for title in ("Bravo post", "Alpha post"):
        r = client.post(
            f"{ADM}/content",
            headers=cms,
            json={**body, "title": title, "slug": title.split()[0].lower()},
        )
        assert r.status_code == 201, r.text
    by_title = client.get(f"{ADM}/content?sort=title", headers=cms).json()["data"]
    assert [i["title"] for i in by_title] == ["Alpha post", "Bravo post"]
    future = (utcnow() + timedelta(days=1)).isoformat()
    none = client.get(f"{ADM}/content", params={"updated_from": future}, headers=cms).json()
    assert none["data"] == [] and none["meta"]["total"] == 0
    assert client.get(f"{ADM}/content?sort=body", headers=cms).status_code == 422

    for _ in range(3):
        client.post("/api/v1/enquiries/contact", json=factories.contact())
    from app.modules.admin import service as admin_service

    monkeypatch.setattr(admin_service, "MAX_EXPORT_ROWS", 2)
    csv = client.get(f"{ADM}/reports/enquiries.csv", headers=sa)
    assert csv.status_code == 200 and csv.text.count("CS-ENQ") == 2  # capped, header kept
