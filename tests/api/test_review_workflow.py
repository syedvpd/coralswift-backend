"""Review checklist/exceptions/stage owners/reconsideration, assessment outcomes, enquiry reply,
staff document upload/replace, replacement-requested status, template version history."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.auth.constants import StaffRole
from app.modules.notifications.models import Notification
from tests import factories
from tests.fakes import RecordingEmail
from tests.helpers import bearer, login, make_staff, onboard_partner, submitted_application

R = "/api/v1/reviewer"
ADM = "/api/v1/admin"
P = "/api/v1/partner"
PUB = "/api/v1/enquiries"


def _staff(client: TestClient, db: Session, settings: Settings, role: StaffRole):  # type: ignore[no-untyped-def]
    user = make_staff(db, settings, role)
    return user, bearer(login(client, user.email)["access_token"])


def _assigned(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> tuple[dict[str, str], Any, dict[str, str], Any, str]:
    _, sa = _staff(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    reviewer, rev = _staff(client, db, settings, StaffRole.PARTNER_REVIEWER)
    partner = onboard_partner(client, db, settings, email)
    app_id = submitted_application(client, partner)
    r = client.post(
        f"{R}/applications/{app_id}/assign", headers=sa, json={"reviewer_id": str(reviewer.id)}
    )
    assert r.status_code == 200, r.text
    return sa, reviewer, rev, partner, app_id


def test_checklist_exceptions_stage_owners_and_scope(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    sa, reviewer, rev, _, app_id = _assigned(client, db, settings, email)
    _, other = _staff(client, db, settings, StaffRole.PARTNER_REVIEWER)
    _, bdm = _staff(client, db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
    base = f"{R}/applications/{app_id}"

    item = {
        "stage": "eligibility_verification",
        "name": "Registration verified",
        "result": "pass",
        "note": "Matches MCA record",
    }
    saved = client.put(f"{base}/checklist", headers=rev, json={"items": [item]})
    assert saved.status_code == 200, saved.text
    assert saved.json()["data"]["checklist"][0]["result"] == "pass"
    assert "score" not in saved.json()["data"]["checklist"][0]
    again = client.put(
        f"{base}/checklist",
        headers=rev,
        json={"items": [{**item, "result": "not_applicable", "note": None}]},
    )
    rows = again.json()["data"]["checklist"]
    assert len(rows) == 1 and rows[0]["result"] == "not_applicable"

    for bad in (
        {**item, "result": "fail", "note": None},  # a failed item needs a reviewer note
        {**item, "result": "yes"},  # old vocabulary
        {**item, "score": 4},  # numerical scoring is not accepted (D9)
        {**item, "stage": "draft"},
        {**item, "stage": "rejected"},
    ):
        assert (
            client.put(f"{base}/checklist", headers=rev, json={"items": [bad]}).status_code == 422
        )
    failed = client.put(
        f"{base}/checklist", headers=rev, json={"items": [{**item, "result": "fail"}]}
    )
    assert failed.status_code == 200
    dup = client.put(f"{base}/checklist", headers=rev, json={"items": [item, item]})
    assert dup.status_code == 422 and dup.json()["error"]["code"] == "DUPLICATE_ITEM"

    # unassigned reviewer, BDM and anonymous users cannot reach the application
    assert client.get(f"{base}/review", headers=other).status_code == 404
    assert client.put(f"{base}/checklist", headers=other, json={"items": [item]}).status_code == 404
    assert client.get(f"{base}/review", headers=bdm).status_code == 403
    assert client.get(f"{base}/review").status_code == 401

    exc = {"rule": "minimum_operating_years", "reason": "Founders ran a predecessor firm"}
    assert client.post(f"{base}/exceptions", headers=rev, json=exc).status_code == 403
    done = client.post(f"{base}/exceptions", headers=sa, json=exc)
    assert done.status_code == 201
    recorded = done.json()["data"]["exceptions"][0]
    assert recorded["rule"] == "minimum_operating_years" and recorded["approver_name"]

    own = client.put(
        f"{base}/stage-owners/capability_review",
        headers=rev,
        json={"owner_user_id": str(reviewer.id), "notes": "Check references first"},
    )
    assert own.status_code == 200
    assert own.json()["data"]["stage_owners"][0]["owner_name"] == "Staff Member"
    partner_user = client.put(
        f"{base}/stage-owners/capability_review",
        headers=rev,
        json={"owner_user_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert partner_user.status_code == 404
    assert client.put(f"{base}/stage-owners/draft", headers=rev, json={}).status_code == 422
    cleared = client.put(
        f"{base}/stage-owners/capability_review", headers=rev, json={"owner_user_id": None}
    )
    assert cleared.json()["data"]["stage_owners"][0]["owner_user_id"] is None
    assert cleared.json()["data"]["stage_owners"][0]["notes"] == "Check references first"


def test_reopen_after_rejection_is_super_admin_only_and_visible_to_partner(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    sa, _, rev, partner, app_id = _assigned(client, db, settings, email)
    base = f"{R}/applications/{app_id}"
    not_terminal = client.post(
        f"{base}/reopen", headers=sa, json={"to_status": "capability_review", "reason": "x"}
    )
    assert (
        not_terminal.status_code == 409 and not_terminal.json()["error"]["code"] == "NOT_REOPENABLE"
    )

    rejected = client.post(
        f"{base}/transition",
        headers=sa,
        json={"to_status": "rejected", "reason": "Insufficient references", "partner_note": "No"},
    )
    assert rejected.status_code == 200, rejected.text
    assert (
        client.post(
            f"{base}/reopen",
            headers=rev,
            json={"to_status": "capability_review", "reason": "retry"},
        ).status_code
        == 403
    )
    for bad in ("rejected", "draft", "information_requested"):
        assert (
            client.post(
                f"{base}/reopen", headers=sa, json={"to_status": bad, "reason": "retry"}
            ).status_code
            == 422
        )
    ok = client.post(
        f"{base}/reopen",
        headers=sa,
        json={"to_status": "capability_review", "reason": "New references supplied"},
    )
    assert ok.status_code == 200, ok.text
    mine = client.get(f"{P}/applications/{app_id}", headers=partner.headers).json()["data"]
    assert mine["status"] == "capability_review" and mine.get("decided_at") is None
    history = client.get(f"{P}/applications/{app_id}/history", headers=partner.headers).text
    assert "reopened for reconsideration" in history
    assert "New references supplied" not in history  # reviewer-only reason stays internal


def _enquiry_id(client: TestClient, sa: dict[str, str], ref: str) -> str:
    rows = client.get(f"{ADM}/enquiries?q={ref}", headers=sa).json()["data"]
    return str(rows[0]["id"])


def test_assessment_outcome_and_reply_respect_strategic_visibility(
    client: TestClient,
    db: Session,
    settings: Settings,
    email: RecordingEmail,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "enquiry_reply_enabled", True)
    _, sa = _staff(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    _, bdm = _staff(client, db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
    _, rev = _staff(client, db, settings, StaffRole.PARTNER_REVIEWER)
    strategic = client.post(f"{PUB}/strategic", json=factories.strategic()).json()["data"]
    general = client.post(
        f"{PUB}/contact", json=factories.contact(business_email="requester@example.net")
    ).json()["data"]
    sid, gid = (
        _enquiry_id(client, sa, strategic["reference_number"]),
        _enquiry_id(client, sa, general["reference_number"]),
    )

    for path in (f"{ADM}/enquiries/{sid}/assessment",):
        assert client.get(path, headers=bdm).status_code == 404
        assert client.post(path, headers=bdm, json={"outcome": "approved"}).status_code == 404
        assert client.post(path, headers=rev, json={"outcome": "approved"}).status_code == 403
    assert (
        client.post(
            f"{ADM}/enquiries/{sid}/reply", headers=bdm, json={"subject": "Hi", "body": "x"}
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"{ADM}/enquiries/{gid}/assessment", headers=bdm, json={"outcome": "proceed"}
        ).status_code
        == 422
    )

    one = client.post(
        f"{ADM}/enquiries/{sid}/assessment",
        headers=sa,
        json={"outcome": "needs_clarification", "note": "n"},
    )
    two = client.post(f"{ADM}/enquiries/{sid}/assessment", headers=sa, json={"outcome": "approved"})
    assert one.status_code == two.status_code == 201
    history = client.get(f"{ADM}/enquiries/{sid}/assessment", headers=sa).json()
    assert [r["outcome"] for r in history["data"]] == ["approved", "needs_clarification"]
    assert history["meta"]["total"] == 2 and history["data"][0]["assessed_by_name"]

    reply = client.post(
        f"{ADM}/enquiries/{gid}/reply",
        headers=bdm,
        json={"subject": "Your enquiry", "body": "Thanks, we will call you on Monday."},
    )
    assert reply.status_code == 201, reply.text
    row = (
        db.execute(select(Notification).where(Notification.template_key == "staff_reply"))
        .scalars()
        .first()
    )
    assert row is not None and row.recipient == "requester@example.net"
    activity = client.get(f"{ADM}/enquiries/{gid}/activity", headers=bdm).text
    assert "followup" in activity.lower() or "communication" in activity.lower()
    row_out: dict[str, Any] = client.get(
        f"{ADM}/enquiries?q={general['reference_number']}", headers=bdm
    ).json()["data"][0]
    assert row_out["first_response_at"] is not None


def test_staff_document_upload_replace_and_replacement_requested(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    sa, _, rev, partner, app_id = _assigned(client, db, settings, email)
    _, other = _staff(client, db, settings, StaffRole.PARTNER_REVIEWER)
    org = partner.organization_id
    up = client.post(
        f"{R}/organizations/{org}/documents",
        headers=rev,
        data={"category": "registration_proof"},
        files={"file": ("reg.pdf", factories.PDF)},
    )
    assert up.status_code == 201, up.text
    doc = up.json()["data"]
    assert doc["current_version"]["scan_status"] == "not_scanned"
    assert doc["current_version"]["upload_status"] == "quarantined"
    assert client.get(f"{P}/documents/{doc['id']}", headers=partner.headers).status_code == 200

    assert (
        client.post(
            f"{R}/organizations/{org}/documents",
            headers=other,
            data={"category": "registration_proof"},
            files={"file": ("reg.pdf", factories.PDF)},
        ).status_code
        == 404
    )
    bad_type = client.post(
        f"{R}/organizations/{org}/documents",
        headers=rev,
        data={"category": "registration_proof"},
        files={"file": ("evil.exe", b"MZ\x90\x00")},
    )
    assert bad_type.status_code in (415, 422)

    newer = client.post(
        f"{R}/organizations/{org}/documents/{doc['id']}/versions",
        headers=rev,
        files={"file": ("reg2.pdf", factories.PDF)},
    )
    assert newer.status_code == 201 and newer.json()["data"]["current_version"]["version_no"] == 2

    review = f"{R}/applications/{app_id}/documents/{doc['id']}/review"
    no_comment = client.post(review, headers=rev, json={"status": "replacement_requested"})
    assert no_comment.status_code == 422
    asked = client.post(
        review, headers=rev, json={"status": "replacement_requested", "comment": "Scan is blurred"}
    )
    assert asked.status_code == 200, asked.text
    seen = client.get(f"{P}/documents/{doc['id']}", headers=partner.headers).json()["data"]
    assert seen["current_version"]["review_status"] == "replacement_requested"
    listing = client.get(f"{ADM}/documents?review_status=replacement_requested", headers=sa)
    assert listing.json()["meta"]["total"] == 1
    audit = client.get(f"{ADM}/audit?action=document.uploaded_by_staff", headers=sa).json()
    assert audit["meta"]["total"] == 1 and audit["data"][0]["actor_type"] == "staff"


def test_template_versions_history_and_activation(
    client: TestClient, db: Session, settings: Settings
) -> None:
    _, sa = _staff(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    _, bdm = _staff(client, db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
    url = f"{ADM}/notification-templates/ack_general"
    body = {"subject": "Hello", "text_body": "Dear $name, thanks.", "html_body": None}
    assert client.put(url, headers=sa, json=body).json()["data"]["version"] >= 1
    first = client.put(url, headers=sa, json={**body, "subject": "Hello v-next"}).json()["data"]
    versions = client.get(f"{url}/versions", headers=sa).json()
    assert versions["data"][0]["version_no"] == first["version"]
    assert {v["subject"] for v in versions["data"]} >= {"Hello", "Hello v-next"}
    oldest = versions["data"][-1]["version_no"]
    back = client.post(f"{url}/versions/{oldest}/activate", headers=sa)
    assert back.status_code == 200 and back.json()["data"]["version"] == first["version"] + 1
    assert back.json()["data"]["subject"] == versions["data"][-1]["subject"]
    assert client.post(f"{url}/versions/9999/activate", headers=sa).status_code == 404
    assert client.get(f"{url}/versions", headers=bdm).status_code == 403


def test_enquiry_reply_is_switched_off_by_default(
    client: TestClient, db: Session, settings: Settings
) -> None:
    assert settings.enquiry_reply_enabled is False
    _, bdm = _staff(client, db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
    general = client.post(f"{PUB}/contact", json=factories.contact()).json()["data"]
    _, sa = _staff(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    gid = _enquiry_id(client, sa, general["reference_number"])
    off = client.post(
        f"{ADM}/enquiries/{gid}/reply", headers=bdm, json={"subject": "Hi", "body": "x"}
    )
    assert off.status_code == 409 and off.json()["error"]["code"] == "FEATURE_DISABLED"
