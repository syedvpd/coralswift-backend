"""D39 approved indicators (calculation, states, publishing), D45 explicit BDM assignment,
D44 enumerations, D10 onboarding template, D3 default targets."""

from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.common.utilities import utcnow
from app.core.config import Settings
from app.modules.applications.models import PortalApplication
from app.modules.auth.constants import StaffRole
from app.modules.enquiries.models import Enquiry
from tests import factories
from tests.fakes import RecordingEmail
from tests.helpers import bearer, login, make_staff, onboard_partner, submitted_application

R = "/api/v1/reviewer"
P = "/api/v1/partner"
ADM = "/api/v1/admin"
PATHWAY = "direct_project_engagement"


def _staff(client: TestClient, db: Session, settings: Settings, role: StaffRole):  # type: ignore[no-untyped-def]
    user = make_staff(db, settings, role)
    return user, bearer(login(client, user.email)["access_token"])


def test_indicator_definitions_states_publish_and_isolation(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    _, sa = _staff(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    a = onboard_partner(client, db, settings, email)
    b = onboard_partner(client, db, settings, email)
    app_id = submitted_application(client, a)
    org, period = a.organization_id, str(utcnow().year)
    compute = f"{R}/organizations/{org}/performance/compute"

    # nothing decided and no required categories defined: both unavailable, nothing invented
    first = client.post(compute, headers=sa, json={"period": period}).json()["data"]
    states = {r["indicator_key"]: r for r in first}
    assert states["application_turnaround_days"]["state"] == "unavailable"
    assert states["document_completeness_percentage"]["state"] == "unavailable"
    assert "(D6)" in states["document_completeness_percentage"]["reason"]
    summary = client.get(f"{P}/performance/summary", headers=a.headers).json()["data"]
    assert [s["state"] for s in summary] == ["unavailable", "unavailable"]
    assert all(s["value"] is None and s["definition"] for s in summary)

    # decided 36 hours after submission -> 1.5 days
    now = utcnow()
    db.execute(
        update(PortalApplication)
        .where(PortalApplication.id == app_id)
        .values(submitted_at=now - timedelta(hours=40), decided_at=now - timedelta(hours=4))
    )
    db.commit()
    # required categories per pathway are an owner setting (D6); define two for this test only
    put = client.put(
        f"{ADM}/settings/required_documents.{PATHWAY}",
        headers=sa,
        json={"value": "registration_proof,operating_history"},
    )
    assert put.status_code == 200, put.text
    try:
        up = client.post(
            f"{P}/documents",
            headers=a.headers,
            data={"category": "registration_proof"},
            files={"file": ("a.pdf", factories.PDF)},
        )
        doc_id = up.json()["data"]["id"]
        zero = client.post(compute, headers=sa, json={"period": period}).json()["data"]
        by_key = {r["indicator_key"]: r for r in zero}
        assert float(by_key["application_turnaround_days"]["value"]) == 1.5
        assert float(by_key["document_completeness_percentage"]["value"]) == 0.0
        accept = client.post(
            f"{R}/applications/{app_id}/documents/{doc_id}/review",
            headers=sa,
            json={"status": "accepted"},
        )
        assert accept.status_code == 200, accept.text
        half = client.post(compute, headers=sa, json={"period": period}).json()["data"]
        by_key = {r["indicator_key"]: r for r in half}
        assert float(by_key["document_completeness_percentage"]["value"]) == 50.0
        assert by_key["application_turnaround_days"]["state"] == "available"
    finally:
        client.delete(f"{ADM}/settings/required_documents.{PATHWAY}", headers=sa)

    # computed entries are unpublished: partners still see "unavailable"
    hidden = client.get(f"{P}/performance/summary", headers=a.headers).json()["data"]
    assert [s["state"] for s in hidden] == ["unavailable", "unavailable"]
    listing = client.get(f"{R}/organizations/{org}/performance", headers=sa).json()["data"]
    assert len(listing) == 2 and not any(e["is_published"] for e in listing)
    for entry in listing:
        assert client.post(f"{R}/performance/{entry['id']}/publish", headers=sa).status_code == 200
    seen = {
        s["indicator_key"]: s
        for s in client.get(f"{P}/performance/summary", headers=a.headers).json()["data"]
    }
    assert all(s["state"] == "published" for s in seen.values())
    assert float(seen["application_turnaround_days"]["value"]) == 1.5
    assert seen["document_completeness_percentage"]["unit"] == "percent"
    other = client.get(f"{P}/performance/summary", headers=b.headers).json()["data"]
    assert [s["state"] for s in other] == ["unavailable", "unavailable"]
    csv = client.get(f"{P}/performance/export.csv", headers=a.headers).text
    assert "application_turnaround_days" in csv and "document_completeness_percentage" in csv
    other_csv = client.get(f"{P}/performance/export.csv", headers=b.headers).text
    assert "application_turnaround_days" not in other_csv
    again = client.post(compute, headers=sa, json={"period": period}).json()["data"]
    # published values are never overwritten; completeness is unavailable again (setting removed)
    assert {r["state"] for r in again} == {"already_published", "unavailable"}
    bad = client.post(
        f"{R}/organizations/{org}/performance",
        headers=sa,
        json={"period": "2026-Q3", "indicator_key": "response_time", "value": "1"},
    )
    assert bad.status_code == 422
    assert client.post(compute, headers=sa, json={"period": "2026-13"}).status_code == 422


def test_bdm_assignment_is_explicit_audited_and_super_admin_only(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    _, sa = _staff(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    bdm_user, bdm = _staff(client, db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
    rev_user, rev = _staff(client, db, settings, StaffRole.PARTNER_REVIEWER)
    p = onboard_partner(client, db, settings, email)
    org = p.organization_id
    url = f"{ADM}/organizations/{org}/bdm-assignments"

    # an assigned originating enquiry no longer grants access (D45: explicit assignment only)
    ref = client.post("/api/v1/enquiries/partner", json=factories.partner()).json()["data"]
    enq = db.query(Enquiry).filter(Enquiry.reference_number == ref["reference_number"]).one()
    enq.assigned_user_id = bdm_user.id
    db.commit()
    proj = client.post(
        f"{R}/projects", headers=sa, json={"organization_id": org, "title": "T"}
    ).json()["data"]["id"]
    assert client.get(f"{R}/projects", headers=bdm).json()["data"] == []
    assert client.get(f"{R}/projects/{proj}", headers=bdm).status_code == 404

    body = {"user_id": str(bdm_user.id)}
    assert client.post(url, headers=bdm, json=body).status_code == 403
    assert client.post(url, headers=rev, json=body).status_code == 403
    assert client.post(url, headers=sa, json={"user_id": str(rev_user.id)}).status_code == 404

    assigned = client.post(url, headers=sa, json=body)
    assert assigned.status_code == 201 and assigned.json()["data"][0]["is_active"] is True
    assert client.post(url, headers=sa, json=body).status_code == 409
    assert client.get(f"{R}/projects/{proj}", headers=bdm).status_code == 200
    assert client.delete(f"{url}/{bdm_user.id}", headers=bdm).status_code == 403

    removed = client.delete(f"{url}/{bdm_user.id}", headers=sa)
    assert removed.status_code == 200
    history = removed.json()["data"]
    assert history[0]["is_active"] is False and history[0]["removed_by_name"]
    assert client.get(f"{R}/projects/{proj}", headers=bdm).status_code == 404
    assert client.delete(f"{url}/{bdm_user.id}", headers=sa).status_code == 404
    actions = client.get(f"{ADM}/audit?organization_id={org}", headers=sa).json()["data"]
    assert {"organization.bdm_assigned", "organization.bdm_unassigned"} <= {
        a["action"] for a in actions
    }
    assert client.post(url, headers=sa, json=body).status_code == 201


def test_d44_enumerations_are_enforced_by_api(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    p = onboard_partner(client, db, settings, email)
    ok = client.put(
        f"{P}/organization",
        headers=p.headers,
        json={"company_type": "llp", "operating_model": "multi_location"},
    )
    assert ok.status_code == 200
    assert ok.json()["data"]["company_type"] == "llp"
    for value in ("Corp", "private limited", ""):
        bad = client.put(f"{P}/organization", headers=p.headers, json={"company_type": value})
        assert bad.status_code == 422, value
    schema: dict[str, Any] = client.get("/openapi.json").json()["components"]["schemas"]
    assert schema["CompanyType"]["enum"] == [
        "private_limited",
        "public_limited",
        "partnership",
        "llp",
        "proprietorship",
        "nonprofit",
        "other",
    ]
    assert schema["OperatingModel"]["enum"] == ["onsite", "remote", "hybrid", "multi_location"]
    assert schema["AssessmentOutcome"]["enum"] == [
        "approved",
        "rejected",
        "needs_clarification",
        "pending",
    ]
    assert schema["IndicatorKey"]["enum"] == [
        "application_turnaround_days",
        "document_completeness_percentage",
    ]


def test_onboarding_template_is_editable_and_copied_with_due_dates(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    _, sa = _staff(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    _, rev = _staff(client, db, settings, StaffRole.PARTNER_REVIEWER)
    a = onboard_partner(client, db, settings, email)
    url = f"{ADM}/onboarding-template"
    assert client.get(url, headers=rev).json()["data"] == []  # nothing is invented
    assert client.put(url, headers=rev, json={"tasks": []}).status_code == 403
    assert (
        client.put(url, headers=sa, json={"tasks": [{"name": "x", "bogus": 1}]}).status_code == 422
    )
    tasks = [
        {"name": "Kick-off call", "due_in_days": 7},
        {"name": "Upload registration", "document_category": "registration_proof"},
    ]
    try:
        assert client.put(url, headers=sa, json={"tasks": tasks}).status_code == 200
        rec = client.post(
            f"{R}/onboarding",
            headers=sa,
            json={"organization_id": a.organization_id, "use_template": True},
        )
        assert rec.status_code == 201, rec.text
        got = rec.json()["data"]["tasks"]
        assert [t["name"] for t in got] == ["Kick-off call", "Upload registration"]
        assert got[0]["due_date"] is not None
        assert got[1]["document_category"] == "registration_proof"
    finally:
        client.put(url, headers=sa, json={"tasks": []})


def test_default_queue_targets_are_24_and_48_hours(
    client: TestClient, db: Session, settings: Settings
) -> None:
    from app.modules.enquiries.routing import (
        DEFAULT_ESCALATION_HOURS,
        DEFAULT_FIRST_RESPONSE_HOURS,
    )

    assert (DEFAULT_FIRST_RESPONSE_HOURS, DEFAULT_ESCALATION_HOURS) == (24, 48)
    _, sa = _staff(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    ref = client.post("/api/v1/enquiries/contact", json=factories.contact()).json()["data"]
    row = client.get(f"{ADM}/enquiries?q={ref['reference_number']}", headers=sa).json()["data"][0]
    assert row["response_due_at"] is not None
