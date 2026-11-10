"""PRD Phase 2 gap closure: additional-document requests with deadline, status and linking."""

from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.utilities import utcnow
from app.core.config import Settings
from app.modules.auth.constants import StaffRole
from app.modules.notifications.models import Notification
from app.modules.partner_documents.models import PartnerDocument
from tests import factories
from tests.fakes import RecordingEmail
from tests.helpers import bearer, login, make_staff, onboard_partner, submitted_application

R = "/api/v1/reviewer"
P = "/api/v1/partner"
CAT = "authorized_contact"


def _h(client: TestClient, db: Session, settings: Settings, role: StaffRole):  # type: ignore[no-untyped-def]
    user = make_staff(db, settings, role)
    return user, bearer(login(client, user.email)["access_token"])


def _upload(
    client: TestClient, headers: dict[str, str], category: str, request_id: str | None = None
) -> Any:
    data = {"category": category, **({"request_id": request_id} if request_id else {})}
    return client.post(
        f"{P}/documents",
        headers=headers,
        data=data,
        files={"file": ("a.pdf", factories.PDF, "application/pdf")},
    )


def test_document_request_lifecycle_visibility_and_linking(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    _, sa = _h(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    reviewer, rev = _h(client, db, settings, StaffRole.PARTNER_REVIEWER)
    _, other_rev = _h(client, db, settings, StaffRole.PARTNER_REVIEWER)
    _, bdm = _h(client, db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
    mine = onboard_partner(client, db, settings, email, org_name="Req One Ltd")
    theirs = onboard_partner(client, db, settings, email, org_name="Req Two Ltd")
    app_id = submitted_application(client, mine)
    client.post(
        f"{R}/applications/{app_id}/assign", headers=sa, json={"reviewer_id": str(reviewer.id)}
    )
    url = f"{R}/applications/{app_id}/document-requests"
    due = (utcnow() + timedelta(days=5)).isoformat()

    assert (
        client.post(url, headers=other_rev, json={"category": CAT, "note": "x"}).status_code == 404
    )  # not theirs
    assert client.post(url, headers=bdm, json={"category": CAT, "note": "x"}).status_code == 403
    past = (utcnow() - timedelta(days=1)).isoformat()
    bad = client.post(url, headers=rev, json={"category": CAT, "note": "x", "due_at": past})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "DUE_IN_PAST"
    assert (
        client.post(url, headers=rev, json={"category": "nonsense", "note": "x"}).status_code == 422
    )
    created = client.post(
        url,
        headers=rev,
        json={"category": CAT, "note": "Please send a signed authority letter", "due_at": due},
    )
    assert created.status_code == 201, created.text
    req = created.json()["data"]
    assert (
        req["status"] == "open"
        and req["created_by_name"] == "Staff Member"
        and req["application_reference"]
    )
    dup = client.post(url, headers=rev, json={"category": CAT, "note": "again"})
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "DUPLICATE_OPEN_REQUEST"
    queued = db.execute(
        select(func.count())
        .select_from(Notification)
        .where(Notification.template_key == "information_requested")
    ).scalar_one()
    assert queued >= 1

    listed = client.get(f"{P}/document-requests", headers=mine.headers).json()
    assert listed["meta"]["open"] == 1 and listed["meta"]["total"] == 1
    item = listed["data"][0]
    assert item["id"] == req["id"] and item["is_overdue"] is False
    assert (
        "created_by_name" not in item and "created_by" not in item and "application_id" not in item
    )
    assert client.get(f"{P}/document-requests", headers=theirs.headers).json()["data"] == []
    assert (
        client.get(f"{P}/document-requests/{req['id']}", headers=theirs.headers).status_code == 404
    )
    assert client.get(f"{P}/document-requests/{req['id']}", headers=mine.headers).status_code == 200
    assert client.get(f"{P}/document-requests").status_code == 401
    assert client.get(f"{P}/document-requests", headers=sa).status_code == 403  # partner area only

    docs_before = db.execute(select(func.count()).select_from(PartnerDocument)).scalar_one()
    wrong = _upload(client, mine.headers, "service_portfolio", req["id"])
    assert wrong.status_code == 422 and wrong.json()["error"]["code"] == "CATEGORY_MISMATCH"
    foreign = _upload(client, theirs.headers, CAT, req["id"])
    assert foreign.status_code == 404
    assert (
        db.execute(select(func.count()).select_from(PartnerDocument)).scalar_one() == docs_before
    )  # no orphans
    ok = _upload(client, mine.headers, CAT, req["id"])
    assert ok.status_code == 201, ok.text
    done = client.get(f"{P}/document-requests/{req['id']}", headers=mine.headers).json()["data"]
    assert (
        done["status"] == "fulfilled" and done["fulfilled_document_id"] == ok.json()["data"]["id"]
    )
    assert (
        client.get(f"{P}/document-requests?status=open", headers=mine.headers).json()["meta"][
            "total"
        ]
        == 0
    )
    again = _upload(client, mine.headers, CAT, req["id"])
    assert again.status_code == 409 and again.json()["error"]["code"] == "REQUEST_CLOSED"
    staff_view = client.get(url, headers=rev).json()
    assert staff_view["meta"]["total"] == 1 and staff_view["data"][0]["status"] == "fulfilled"
    assert client.get(url, headers=other_rev).status_code == 404


def test_cancelled_and_overdue_requests(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    _, sa = _h(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    partner = onboard_partner(client, db, settings, email, org_name="Cancel Ltd")
    app_id = submitted_application(client, partner)
    url = f"{R}/applications/{app_id}/document-requests"
    req = client.post(url, headers=sa, json={"category": CAT, "note": "n"}).json()["data"]
    cancel = client.post(f"{R}/document-requests/{req['id']}/cancel", headers=sa)
    assert cancel.status_code == 200 and cancel.json()["data"]["status"] == "cancelled"
    assert client.post(f"{R}/document-requests/{req['id']}/cancel", headers=sa).status_code == 409
    blocked = _upload(client, partner.headers, CAT, req["id"])
    assert blocked.status_code == 409
    assert (
        client.post(
            f"{R}/document-requests/00000000-0000-0000-0000-000000000000/cancel", headers=sa
        ).status_code
        == 404
    )
    again = client.post(url, headers=sa, json={"category": CAT, "note": "second"})
    assert again.status_code == 201  # a cancelled request frees the category
