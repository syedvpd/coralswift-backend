"""Projects, organisation inbox, discussions / meetings / follow-ups (partner portal)."""

from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.common.utilities import utcnow
from app.core.config import Settings
from app.modules.auth.constants import StaffRole
from tests import factories
from tests.fakes import RecordingEmail
from tests.helpers import bearer, login, make_staff, onboard_partner, submitted_application

R = "/api/v1/reviewer"
P = "/api/v1/partner"
MISSING = "00000000-0000-0000-0000-000000000000"


def _staff(client: TestClient, db: Session, settings: Settings, role: StaffRole):  # type: ignore[no-untyped-def]
    user = make_staff(db, settings, role)
    return user, bearer(login(client, user.email)["access_token"])


def _doc(client: TestClient, partner: Any) -> str:
    r = client.post(
        f"{P}/documents",
        headers=partner.headers,
        data={"category": "registration_proof"},
        files={"file": ("reg.pdf", factories.PDF)},
    )
    assert r.status_code == 201, r.text
    return str(r.json()["data"]["id"])


def test_project_visible_only_after_share_and_only_to_its_organisation(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    _, sa = _staff(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    a = onboard_partner(client, db, settings, email, org_name="Alpha Ltd")
    b = onboard_partner(client, db, settings, email, org_name="Bravo Ltd")
    created = client.post(
        f"{R}/projects",
        headers=sa,
        json={
            "organization_id": a.organization_id,
            "title": "Pilot dispatch",
            "category": "it_services",
            "contact_name": "Ravi Kumar",
            "milestones": [{"title": "Kick-off", "due_date": "2026-12-01"}],
        },
    )
    assert created.status_code == 201, created.text
    pid = created.json()["data"]["id"]
    assert created.json()["data"]["is_shared"] is False

    assert client.get(f"{P}/projects", headers=a.headers).json()["data"] == []
    assert client.get(f"{P}/projects/{pid}", headers=a.headers).status_code == 404

    assert client.post(f"{R}/projects/{pid}/share", headers=sa).status_code == 200
    mine = client.get(f"{P}/projects", headers=a.headers).json()
    assert mine["meta"]["total"] == 1 and mine["data"][0]["status"] == "awaiting_partner"
    assert mine["data"][0]["status_label"] == "Awaiting your response"
    detail = client.get(f"{P}/projects/{pid}", headers=a.headers).json()["data"]
    assert (
        detail["contact"]["name"] == "Ravi Kumar" and detail["milestones"][0]["title"] == "Kick-off"
    )

    # other organisation: empty list, 404 on detail and every action
    assert client.get(f"{P}/projects", headers=b.headers).json()["data"] == []
    for path in ("acknowledge", "confirm", "respond", "submit-information"):
        assert (
            client.post(f"{P}/projects/{pid}/{path}", headers=b.headers, json={}).status_code == 404
        )
    assert client.get(f"{P}/projects/{pid}", headers=b.headers).status_code == 404
    assert client.get(f"{P}/projects").status_code == 401

    assert client.post(f"{R}/projects/{pid}/unshare", headers=sa).status_code == 200
    assert client.get(f"{P}/projects/{pid}", headers=a.headers).status_code == 404


def test_project_partner_actions_documents_and_closed_state(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    _, sa = _staff(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    a = onboard_partner(client, db, settings, email)
    b = onboard_partner(client, db, settings, email)
    pid = client.post(
        f"{R}/projects", headers=sa, json={"organization_id": a.organization_id, "title": "Scope"}
    ).json()["data"]["id"]
    client.post(f"{R}/projects/{pid}/share", headers=sa)

    ack = client.post(f"{P}/projects/{pid}/acknowledge", headers=a.headers, json={})
    assert ack.status_code == 200 and ack.json()["data"]["status"] == "acknowledged"
    assert client.post(f"{P}/projects/{pid}/respond", headers=a.headers, json={}).status_code == 422
    assert (
        client.post(
            f"{P}/projects/{pid}/respond",
            headers=a.headers,
            json={"body": "We can start in January"},
        ).status_code
        == 200
    )

    own_doc, foreign_doc = _doc(client, a), _doc(client, b)
    bad = client.post(
        f"{P}/projects/{pid}/submit-information",
        headers=a.headers,
        json={"body": "x", "document_ids": [foreign_doc]},
    )
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "INVALID_DOCUMENT"
    good = client.post(
        f"{P}/projects/{pid}/submit-information",
        headers=a.headers,
        json={"body": "Registration attached", "document_ids": [own_doc]},
    )
    assert good.status_code == 200 and [d["id"] for d in good.json()["data"]["documents"]] == [
        own_doc
    ]

    conf = client.post(f"{P}/projects/{pid}/confirm", headers=a.headers, json={})
    assert conf.status_code == 200 and conf.json()["data"]["status"] == "confirmed"
    again = client.post(f"{P}/projects/{pid}/confirm", headers=a.headers, json={})
    assert again.status_code == 409 and again.json()["error"]["code"] == "ALREADY_CONFIRMED"

    staff_view = client.get(f"{R}/projects/{pid}", headers=sa).json()["data"]
    assert {r["kind"] for r in staff_view["responses"]} == {
        "acknowledge",
        "respond",
        "submit_information",
        "confirm",
    }

    assert (
        client.patch(f"{R}/projects/{pid}", headers=sa, json={"status": "completed"}).status_code
        == 200
    )
    closed = client.post(f"{P}/projects/{pid}/respond", headers=a.headers, json={"body": "late"})
    assert closed.status_code == 409 and closed.json()["error"]["code"] == "PROJECT_CLOSED"
    assert client.patch(f"{R}/projects/{pid}", headers=sa, json={"title": None}).status_code == 422


def test_staff_scope_reviewer_sees_only_assigned_organisations(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    _, sa = _staff(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    reviewer, rev = _staff(client, db, settings, StaffRole.PARTNER_REVIEWER)
    _, bdm = _staff(client, db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
    a = onboard_partner(client, db, settings, email)
    b = onboard_partner(client, db, settings, email)
    app_id = submitted_application(client, a)
    client.post(
        f"{R}/applications/{app_id}/assign", headers=sa, json={"reviewer_id": str(reviewer.id)}
    )

    ok = client.post(
        f"{R}/projects", headers=rev, json={"organization_id": a.organization_id, "title": "T"}
    )
    assert ok.status_code == 201
    foreign = client.post(
        f"{R}/projects", headers=rev, json={"organization_id": b.organization_id, "title": "T"}
    )
    assert foreign.status_code == 404
    other_id = client.post(
        f"{R}/projects", headers=sa, json={"organization_id": b.organization_id, "title": "B"}
    ).json()["data"]["id"]
    assert client.get(f"{R}/projects/{other_id}", headers=rev).status_code == 404
    assert [p["id"] for p in client.get(f"{R}/projects", headers=rev).json()["data"]] == [
        ok.json()["data"]["id"]
    ]
    # BDMs read assigned organisations only (D45); this one has none
    assert client.get(f"{R}/projects", headers=bdm).json()["data"] == []
    assert client.get(f"{R}/collaboration", headers=bdm).json()["data"] == []
    assert client.get(f"{R}/projects/{MISSING}", headers=sa).status_code == 404


def test_inbox_isolation_read_state_attachments_and_internal_notes(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    _, sa = _staff(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    a = onboard_partner(client, db, settings, email)
    b = onboard_partner(client, db, settings, email)
    doc = _doc(client, a)
    visible = client.post(
        f"{R}/partner-messages",
        headers=sa,
        json={
            "organization_id": a.organization_id,
            "subject": "Welcome",
            "body": "Hello",
            "document_ids": [doc],
        },
    )
    assert (
        visible.status_code == 201 and visible.json()["data"]["sender_label"] == "CoralSwift Team"
    )
    note = client.post(
        f"{R}/partner-messages",
        headers=sa,
        json={
            "organization_id": a.organization_id,
            "subject": "Internal",
            "body": "do not show",
            "partner_visible": False,
        },
    )
    assert note.status_code == 201
    foreign_attachment = client.post(
        f"{R}/partner-messages",
        headers=sa,
        json={
            "organization_id": b.organization_id,
            "subject": "x",
            "body": "y",
            "document_ids": [doc],
        },
    )
    assert foreign_attachment.status_code == 422

    box = client.get(f"{P}/messages", headers=a.headers).json()
    assert box["meta"]["unread"] == 1 and [m["subject"] for m in box["data"]] == ["Welcome"]
    mid = visible.json()["data"]["id"]
    detail = client.get(f"{P}/messages/{mid}", headers=a.headers).json()["data"]
    assert detail["is_read"] is False and detail["attachments"][0]["document_id"] == doc
    assert client.post(f"{P}/messages/{mid}/read", headers=a.headers).status_code == 200
    assert client.get(f"{P}/messages", headers=a.headers).json()["meta"]["unread"] == 0
    assert client.post(f"{P}/messages/{mid}/unread", headers=a.headers).status_code == 200
    assert client.get(f"{P}/messages?unread=true", headers=a.headers).json()["meta"]["total"] == 1

    assert (
        client.get(f"{P}/messages/{note.json()['data']['id']}", headers=a.headers).status_code
        == 404
    )
    assert client.get(f"{P}/messages/{mid}", headers=b.headers).status_code == 404
    assert client.post(f"{P}/messages/{mid}/read", headers=b.headers).status_code == 404
    assert client.get(f"{P}/messages", headers=b.headers).json()["data"] == []

    sent = client.post(
        f"{P}/messages",
        headers=a.headers,
        json={"subject": "Question", "body": "When?", "document_ids": [doc]},
    )
    assert sent.status_code == 201 and sent.json()["data"]["direction"] == "inbound"
    assert (
        client.post(
            f"{P}/messages",
            headers=a.headers,
            json={"subject": "x", "body": "y", "project_id": MISSING},
        ).status_code
        == 404
    )
    staff_box = client.get(f"{R}/partner-messages?direction=inbound", headers=sa).json()["data"]
    assert [m["subject"] for m in staff_box] == ["Question"]


def test_discussions_meetings_followups_shared_only_actions_and_admin_visibility(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    _, sa = _staff(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    a = onboard_partner(client, db, settings, email)
    b = onboard_partner(client, db, settings, email)
    start = (utcnow() + timedelta(days=3)).isoformat()

    def make(kind: str, **extra: Any) -> str:
        r = client.post(
            f"{R}/collaboration",
            headers=sa,
            json={
                "organization_id": a.organization_id,
                "kind": kind,
                "title": f"{kind} one",
                **extra,
            },
        )
        assert r.status_code == 201, r.text
        return str(r.json()["data"]["id"])

    discussion = make("discussion", body="Scope question")
    meeting = make("meeting", starts_at=start, location="Video call")
    follow = make("follow_up", due_at=start)
    bad_meeting = client.post(
        f"{R}/collaboration",
        headers=sa,
        json={"organization_id": a.organization_id, "kind": "meeting", "title": "no start"},
    )
    assert bad_meeting.status_code == 422

    for path in ("discussions", "meetings", "follow-ups"):
        assert client.get(f"{P}/{path}", headers=a.headers).json()["data"] == []
    assert client.get(f"{P}/meetings/{meeting}", headers=a.headers).status_code == 404

    for item in (discussion, meeting, follow):
        assert client.post(f"{R}/collaboration/{item}/share", headers=sa).status_code == 200
    assert client.get(f"{P}/meetings", headers=a.headers).json()["meta"]["total"] == 1
    assert client.get(f"{P}/meetings/{meeting}", headers=b.headers).status_code == 404
    # a meeting id through the discussions route is not found: kinds do not cross
    assert client.get(f"{P}/discussions/{meeting}", headers=a.headers).status_code == 404

    d = client.get(f"{P}/meetings/{meeting}", headers=a.headers).json()["data"]
    assert d["status"] == "awaiting_partner" and set(d["allowed_actions"]) == {
        "reply",
        "accept",
        "decline",
    }
    accept = client.post(
        f"{P}/meetings/{meeting}/respond", headers=a.headers, json={"action": "accept"}
    )
    assert accept.status_code == 200 and accept.json()["data"]["status"] == "responded"
    wrong = client.post(
        f"{P}/discussions/{discussion}/respond", headers=a.headers, json={"action": "accept"}
    )
    assert wrong.status_code == 422 and wrong.json()["error"]["code"] == "ACTION_NOT_ALLOWED"
    assert (
        client.post(
            f"{P}/discussions/{discussion}/respond", headers=a.headers, json={"action": "reply"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"{P}/discussions/{discussion}/respond",
            headers=b.headers,
            json={"action": "reply", "body": "hi"},
        ).status_code
        == 404
    )
    reply = client.post(
        f"{P}/discussions/{discussion}/respond",
        headers=a.headers,
        json={"action": "reply", "body": "Answer"},
    )
    assert reply.status_code == 200 and reply.json()["data"]["responses"][0]["from_partner"] is True
    done = client.post(
        f"{P}/follow-ups/{follow}/respond", headers=a.headers, json={"action": "complete"}
    )
    assert (
        done.json()["data"]["status"] == "completed"
        and done.json()["data"]["allowed_actions"] == []
    )
    closed = client.post(
        f"{P}/follow-ups/{follow}/respond", headers=a.headers, json={"action": "reply", "body": "x"}
    )
    assert closed.status_code == 409 and closed.json()["error"]["code"] == "ITEM_CLOSED"

    answered = client.get(f"{R}/collaboration?has_partner_response=true", headers=sa).json()
    assert answered["meta"]["total"] == 3
    staff_detail = client.get(f"{R}/collaboration/{discussion}", headers=sa).json()["data"]
    assert staff_detail["responses"][0]["body"] == "Answer"
    staff_reply = client.post(
        f"{R}/collaboration/{discussion}/reply", headers=sa, json={"body": "Thanks"}
    )
    assert (
        staff_reply.status_code == 200
        and staff_reply.json()["data"]["status"] == "awaiting_partner"
    )
    seen = client.get(f"{P}/discussions/{discussion}", headers=a.headers).json()["data"][
        "responses"
    ]
    assert [r["author"] for r in seen][-1] == "CoralSwift Team"  # staff never named to partners
    assert (
        client.post(f"{R}/collaboration/{discussion}/close?outcome=open", headers=sa).status_code
        == 422
    )
    assert (
        client.post(
            f"{R}/collaboration/{discussion}/close?outcome=cancelled", headers=sa
        ).status_code
        == 200
    )
