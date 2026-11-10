"""Gap closure: document queue, typed settings/launch readiness, security policy."""

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.common.utilities import utcnow
from app.core.config import Settings
from app.modules.auth.constants import StaffRole
from tests import factories
from tests.fakes import RecordingEmail
from tests.helpers import bearer, login, make_staff, onboard_partner, submitted_application

ADM = "/api/v1/admin"
R = "/api/v1/reviewer"


def _h(client: TestClient, db: Session, settings: Settings, role: StaffRole):  # type: ignore[no-untyped-def]
    user = make_staff(db, settings, role)
    return user, bearer(login(client, user.email)["access_token"])


def test_document_queue_scope_filters_and_no_storage_details(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    _, sa = _h(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    reviewer, rev = _h(client, db, settings, StaffRole.PARTNER_REVIEWER)
    _, bdm = _h(client, db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
    p1 = onboard_partner(client, db, settings, email, org_name="Docs One Ltd")
    p2 = onboard_partner(client, db, settings, email, org_name="Docs Two Ltd")
    a1 = submitted_application(client, p1)
    submitted_application(client, p2)

    everything = client.get(f"{ADM}/documents?page_size=100", headers=sa).json()
    assert everything["meta"]["total"] == len(everything["data"]) >= 14  # 7 required each
    row = everything["data"][0]
    assert "storage_key" not in row and "checksum" not in row
    assert row["upload_status"] == "quarantined"  # stored, never scanned
    assert {"organization_name", "category", "review_status", "version_no", "purged"} <= set(row)
    assert client.get(f"{ADM}/documents", headers=bdm).status_code == 403
    assert client.get(f"{ADM}/documents", headers=p1.headers).status_code == 403
    assert client.get(f"{ADM}/documents").status_code == 401

    assert client.get(f"{ADM}/documents", headers=rev).json()["data"] == []  # nothing assigned yet
    client.post(f"{R}/applications/{a1}/assign", headers=sa, json={"reviewer_id": str(reviewer.id)})
    mine = client.get(f"{ADM}/documents?page_size=100", headers=rev).json()
    assert mine["meta"]["total"] >= 7 and {d["organization_name"] for d in mine["data"]} == {
        "Docs One Ltd"
    }
    history = client.get(f"{ADM}/documents/{mine['data'][0]['document_id']}/history", headers=rev)
    assert history.status_code == 200
    assert history.json()["data"][0]["review_status"] == "pending"

    org1 = mine["data"][0]["organization_id"]
    assert (
        client.get(f"{ADM}/documents?organization_id={org1}", headers=sa).json()["meta"]["total"]
        == mine["meta"]["total"]
    )
    cat = client.get(f"{ADM}/documents?category=financial_statements", headers=sa).json()
    assert cat["meta"]["total"] == 2 and all(
        d["category"] == "financial_statements" for d in cat["data"]
    )
    assert (
        client.get(f"{ADM}/documents?review_status=accepted", headers=sa).json()["meta"]["total"]
        == 0
    )
    assert (
        client.get(f"{ADM}/documents?upload_status=quarantined", headers=sa).json()["meta"]["total"]
        >= 14
    )
    assert (
        client.get(f"{ADM}/documents?upload_status=clean", headers=sa).json()["meta"]["total"] == 0
    )
    assert client.get(f"{ADM}/documents?q=two", headers=sa).json()["meta"]["total"] >= 7
    soon = (utcnow() + timedelta(days=400)).date().isoformat()
    assert client.get(f"{ADM}/documents?expires_before={soon}", headers=sa).status_code == 200
    asc = client.get(f"{ADM}/documents?sort=uploaded_at&page_size=100", headers=sa).json()["data"]
    desc = client.get(f"{ADM}/documents?sort=-uploaded_at&page_size=100", headers=sa).json()["data"]
    assert [d["document_id"] for d in asc] == [d["document_id"] for d in reversed(desc)]
    assert client.get(f"{ADM}/documents?category=made_up", headers=sa).status_code == 422
    assert client.get(f"{ADM}/documents?sort=storage_key", headers=sa).status_code == 422


def test_settings_and_launch_readiness_are_typed(
    client: TestClient, db: Session, settings: Settings
) -> None:
    _, sa = _h(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    _, bdm = _h(client, db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
    s = client.get(f"{ADM}/settings", headers=sa).json()["data"]
    assert set(s) == {"values", "allowed_keys", "definitions"}
    kinds = {d["key"]: d["value_kind"] for d in s["definitions"]}
    assert kinds["sla.general"] == "integer" and kinds["ack_promise_enabled"] == "boolean"
    assert (
        kinds["escalation.email.general"] == "email" and kinds["route.owner.general"] == "user_id"
    )
    assert {d["key"] for d in s["definitions"]} == set(s["allowed_keys"])
    assert client.get(f"{ADM}/settings", headers=bdm).status_code == 403

    lr = client.get(f"{ADM}/launch-readiness", headers=sa).json()["data"]
    assert lr["ready"] is False and lr["pending_items"]
    assert set(lr) == {"contact", "queues", "ready", "pending_items"}
    assert set(next(iter(lr["queues"].values()))) == {"owner", "sla_hours", "escalation"}
    assert all(v in ("confirmed", "omitted", "pending") for v in lr["contact"].values())
    assert "general.sla_hours" in lr["pending_items"]
    client.put(f"{ADM}/settings/sla.general", headers=sa, json={"value": "8"})
    after = client.get(f"{ADM}/launch-readiness", headers=sa).json()["data"]
    assert after["queues"]["general"]["sla_hours"] is True
    assert "general.sla_hours" not in after["pending_items"]
    assert client.get(f"{ADM}/launch-readiness", headers=bdm).status_code == 403


def test_security_policy_is_read_only_super_admin_only_and_has_no_secrets(
    client: TestClient, db: Session, settings: Settings
) -> None:
    _, sa = _h(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    _, rev = _h(client, db, settings, StaffRole.PARTNER_REVIEWER)
    body = client.get(f"{ADM}/security-policy", headers=sa)
    assert body.status_code == 200
    p = body.json()["data"]
    assert p["password_min_length"] == settings.password_min_length
    assert p["max_upload_bytes"] == settings.max_upload_bytes and p["partner_mfa"] == "optional"
    assert {"pdf", "png", "docx"} <= set(p["allowed_upload_types"])
    assert p["invitation_link_path"] == "/activate?token="
    assert p["reset_link_path"] == "/reset-password?token="
    assert "quarantined" in p["malware_scanning"]
    text = body.text.lower()
    assert all(w not in text for w in ("secret_key", "database_url", "api_key", "access_key"))
    assert client.get(f"{ADM}/security-policy", headers=rev).status_code == 403
    assert client.put(f"{ADM}/security-policy", headers=sa, json={}).status_code == 405
    assert factories.PDF  # (upload types are enforced by the upload tests)
