"""Partner team management, notification preferences, account closure, onboarding checklist."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.auth.constants import StaffRole
from tests.fakes import RecordingEmail
from tests.helpers import (
    PASSWORD,
    bearer,
    last_token,
    login,
    make_staff,
    onboard_partner,
    submitted_application,
)

P = "/api/v1/partner"
R = "/api/v1/reviewer"
A = "/api/v1/auth"


def _staff(client: TestClient, db: Session, settings: Settings, role: StaffRole):  # type: ignore[no-untyped-def]
    user = make_staff(db, settings, role)
    return user, bearer(login(client, user.email)["access_token"])


def _add_member(client: TestClient, owner, email_fake: RecordingEmail, address: str):  # type: ignore[no-untyped-def]
    r = client.post(
        f"{P}/team/invitations",
        headers=owner.headers,
        json={"email": address, "full_name": "Colleague One"},
    )
    assert r.status_code == 201, r.text
    token = last_token(email_fake, address)
    assert (
        client.post(
            f"{A}/invitations/accept", json={"token": token, "password": PASSWORD}
        ).status_code
        == 200
    )
    return r.json()["data"]["id"], bearer(login(client, address)["access_token"])


def test_team_lifecycle_roles_and_protections(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    owner = onboard_partner(client, db, settings, email)
    other_org = onboard_partner(client, db, settings, email)

    me = client.get(f"{A}/me", headers=owner.headers).json()["data"]
    assert me["partner_role"] == "owner" and me["permissions"] == ["team.manage"]

    pending = client.post(
        f"{P}/team/invitations",
        headers=owner.headers,
        json={"email": "new.person@example.com", "full_name": "New Person"},
    )
    assert pending.status_code == 201 and pending.json()["data"]["account_status"] == "invited"
    pid = pending.json()["data"]["id"]
    assert client.post(f"{P}/team/{pid}/resend", headers=owner.headers).status_code == 200
    # a different organisation cannot see or touch this member
    assert client.get(f"{P}/team/{pid}", headers=other_org.headers).status_code == 404
    assert client.post(f"{P}/team/{pid}/cancel", headers=other_org.headers).status_code == 404
    assert client.post(f"{P}/team/{pid}/cancel", headers=owner.headers).status_code == 200
    assert client.get(f"{P}/team/{pid}", headers=owner.headers).status_code == 404

    mid, member = _add_member(client, owner, email, "colleague@example.com")
    team = client.get(f"{P}/team", headers=owner.headers).json()["data"]
    assert {m["role"] for m in team} == {"owner", "member"} and len(team) == 2
    assert client.get(f"{A}/me", headers=member).json()["data"]["permissions"] == []

    # a member cannot manage the team or elevate themselves
    assert client.get(f"{P}/team/{mid}", headers=member).status_code == 200
    for call in (
        client.post(
            f"{P}/team/invitations",
            headers=member,
            json={"email": "x@example.com", "full_name": "X Y"},
        ),
        client.patch(f"{P}/team/{mid}/role", headers=member, json={"role": "owner"}),
        client.post(f"{P}/team/{mid}/deactivate", headers=member),
        client.delete(f"{P}/team/{mid}", headers=member),
    ):
        assert call.status_code == 403

    owner_id = next(m["id"] for m in team if m["is_you"])
    self_role = client.patch(
        f"{P}/team/{owner_id}/role", headers=owner.headers, json={"role": "member"}
    )
    assert self_role.status_code == 409 and self_role.json()["error"]["code"] == "SELF_CHANGE"
    assert client.post(f"{P}/team/{owner_id}/deactivate", headers=owner.headers).status_code == 409
    assert client.delete(f"{P}/team/{owner_id}", headers=owner.headers).status_code == 409

    # promote the colleague; the original owner can then be demoted by the new owner
    assert (
        client.patch(
            f"{P}/team/{mid}/role", headers=owner.headers, json={"role": "owner"}
        ).status_code
        == 200
    )
    assert client.get(f"{A}/me", headers=member).status_code == 401  # role change signs them out
    new_owner = bearer(login(client, "colleague@example.com")["access_token"])
    demoted = client.patch(f"{P}/team/{owner_id}/role", headers=new_owner, json={"role": "member"})
    assert demoted.status_code == 200
    # the only owner can never be demoted, removed or deactivated (self protections apply first)
    assert client.delete(f"{P}/team/{mid}", headers=new_owner).status_code == 409

    deact = client.post(f"{P}/team/{owner_id}/deactivate", headers=new_owner)
    assert deact.status_code == 200 and deact.json()["data"]["account_status"] == "deactivated"
    assert (
        client.post(f"{A}/login", json={"email": owner.email, "password": PASSWORD}).status_code
        == 403
    )
    again = client.post(f"{P}/team/{owner_id}/activate", headers=new_owner)
    assert again.status_code == 200 and again.json()["data"]["account_status"] == "active"

    assert client.delete(f"{P}/team/{owner_id}", headers=new_owner).status_code == 200
    assert len(client.get(f"{P}/team", headers=new_owner).json()["data"]) == 1
    assert (
        client.post(f"{A}/login", json={"email": owner.email, "password": PASSWORD}).status_code
        == 403
    )


def test_ownership_transfer_and_last_owner_guard(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    owner = onboard_partner(client, db, settings, email)
    mid, member = _add_member(client, owner, email, "heir@example.com")
    team = client.get(f"{P}/team", headers=owner.headers).json()["data"]
    me_id = next(m["id"] for m in team if m["is_you"])
    assert (
        client.post(
            f"{P}/team/transfer-ownership", headers=owner.headers, json={"membership_id": me_id}
        ).status_code
        == 409
    )
    moved = client.post(
        f"{P}/team/transfer-ownership", headers=owner.headers, json={"membership_id": mid}
    )
    assert moved.status_code == 200 and {m["role"] for m in moved.json()["data"]} == {
        "owner",
        "member",
    }
    assert (
        client.post(
            f"{P}/team/invitations",
            headers=owner.headers,
            json={"email": "z@example.com", "full_name": "Zed Zed"},
        ).status_code
        == 403
    )
    # only the new owner is left to demote; demoting them would orphan the organisation
    new_owner = bearer(login(client, "heir@example.com")["access_token"])
    assert (
        client.patch(
            f"{P}/team/{me_id}/role", headers=new_owner, json={"role": "owner"}
        ).status_code
        == 200
    )


def test_notification_preferences_mandatory_cannot_be_disabled_and_mute_applies(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    p = onboard_partner(client, db, settings, email)
    base = client.get(f"{P}/notification-preferences", headers=p.headers).json()["data"]
    assert base["mandatory"] == ["account", "application"]
    assert base["categories"]["acknowledgement"] is True
    bad = client.put(
        f"{P}/notification-preferences", headers=p.headers, json={"categories": {"account": False}}
    )
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "MANDATORY_NOTICE"
    unknown = client.put(
        f"{P}/notification-preferences", headers=p.headers, json={"categories": {"nope": False}}
    )
    assert unknown.status_code == 422
    ok = client.put(
        f"{P}/notification-preferences",
        headers=p.headers,
        json={"categories": {"acknowledgement": False}},
    )
    assert ok.status_code == 200 and ok.json()["data"]["categories"]["acknowledgement"] is False
    assert client.get(f"{P}/notification-preferences").status_code == 401

    from app.modules.notifications.constants import NotificationType, TemplateKey
    from app.modules.notifications.service import queue_notification

    queue_notification(
        db,
        recipient=p.email,
        kind=NotificationType.ACKNOWLEDGEMENT,
        template=TemplateKey.ACK_GENERAL,
        context={"reference": "X"},
        dedupe_key="mute-test-1",
    )
    queue_notification(
        db,
        recipient=p.email,
        kind=NotificationType.APPLICATION,
        template=TemplateKey.APPLICATION_DECISION,
        context={"reference": "X"},
        dedupe_key="mute-test-3",
    )
    queue_notification(
        db,
        recipient=p.email,
        kind=NotificationType.ACCOUNT,
        template=TemplateKey.PASSWORD_RESET,
        context={"link": "x"},
        dedupe_key="mute-test-2",
    )
    db.commit()
    from sqlalchemy import select

    from app.modules.notifications.models import Notification

    keys = set(
        db.execute(
            select(Notification.dedupe_key).where(Notification.dedupe_key.like("mute-test-%"))
        ).scalars()
    )
    # acknowledgement (optional) was muted; account and application-decision mail still queue
    assert keys == {"mute-test-2", "mute-test-3"}


def test_account_closure_blockers_password_and_request(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    p = onboard_partner(client, db, settings, email)
    submitted_application(client, p)
    preview = client.get(f"{P}/account-closure/preview", headers=p.headers).json()["data"]
    assert preview["can_close"] is False and "OPEN_APPLICATIONS" in {
        b["code"] for b in preview["blockers"]
    }
    blocked = client.post(f"{P}/account-closure", headers=p.headers, json={"password": PASSWORD})
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "CLOSURE_BLOCKED"

    q = onboard_partner(client, db, settings, email)
    wrong = client.post(
        f"{P}/account-closure", headers=q.headers, json={"password": "not-the-password-1"}
    )
    assert wrong.status_code == 400
    done = client.post(
        f"{P}/account-closure",
        headers=q.headers,
        json={"password": PASSWORD, "reason": "Winding up"},
    )
    assert done.status_code == 201 and done.json()["data"]["reference"].startswith("PR-")
    mine = client.get(f"{P}/privacy-requests", headers=q.headers).json()["data"]
    assert mine[0]["kind"] == "deletion"


def test_onboarding_record_checklist_visibility_and_isolation(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    _, sa = _staff(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    _, bdm = _staff(client, db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
    a = onboard_partner(client, db, settings, email)
    b = onboard_partner(client, db, settings, email)
    assert client.get(f"{P}/onboarding", headers=a.headers).json()["data"] is None

    rec = client.post(f"{R}/onboarding", headers=sa, json={"organization_id": a.organization_id})
    assert rec.status_code == 201, rec.text
    rid = rec.json()["data"]["id"]
    assert (
        client.post(
            f"{R}/onboarding", headers=sa, json={"organization_id": a.organization_id}
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"{R}/onboarding", headers=bdm, json={"organization_id": a.organization_id}
        ).status_code
        == 403
    )

    visible = client.post(
        f"{R}/onboarding/{rid}/tasks",
        headers=sa,
        json={
            "name": "Upload registration",
            "required_action": "Upload proof",
            "due_date": "2020-01-01",
            "document_category": "registration_proof",
        },
    )
    assert visible.status_code == 201
    client.post(
        f"{R}/onboarding/{rid}/tasks",
        headers=sa,
        json={"name": "Internal check", "partner_visible": False},
    )

    mine = client.get(f"{P}/onboarding", headers=a.headers).json()["data"]
    assert [t["name"] for t in mine["tasks"]] == ["Upload registration"]
    assert (
        mine["tasks"][0]["is_overdue"] is True
        and mine["tasks"][0]["document_category"] == "registration_proof"
    )
    assert mine["progress"] == {"total": 1, "completed": 0} and mine["provisioned_at"]
    assert client.get(f"{P}/onboarding", headers=b.headers).json()["data"] is None

    staff_view = client.get(f"{R}/onboarding/{rid}", headers=sa).json()["data"]
    assert len(staff_view["tasks"]) == 2
    blocked = client.post(f"{R}/onboarding/{rid}/complete", headers=sa)
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "TASKS_OPEN"
    for t in staff_view["tasks"]:
        up = client.patch(
            f"{R}/onboarding/{rid}/tasks/{t['id']}", headers=sa, json={"status": "completed"}
        )
        assert up.status_code == 200
    assert (
        client.patch(
            f"{R}/onboarding/{rid}/tasks/{staff_view['tasks'][0]['id']}",
            headers=sa,
            json={"name": None},
        ).status_code
        == 422
    )
    done = client.post(f"{R}/onboarding/{rid}/complete", headers=sa)
    assert done.status_code == 200 and done.json()["data"]["completed_at"]
    assert client.get(f"{P}/onboarding", headers=a.headers).json()["data"]["progress"] == {
        "total": 1,
        "completed": 1,
    }
