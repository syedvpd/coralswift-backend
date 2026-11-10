from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.organizations.models import PartnerOrganization, PartnerProfileRevision
from tests.fakes import RecordingEmail
from tests.helpers import onboard_partner

ORG = "/api/v1/partner/organization"

FULL = {
    "registration_number": "U72200TG2015PTC123456",
    "year_established": 2015,
    "employee_count": 120,
    "annual_turnover_inr_crore": "5.50",
    "registered_address": "12 MG Road, Hyderabad",
    "country": "in",
    "website": "https://rao.example.com",
    "service_categories": ["erp", "web_applications"],
    "technical_capabilities": "Python, Java, cloud",
    "infrastructure_summary": "Two delivery centres",
    "business_description": "ERP and web delivery partner",
    "client_references": [
        {"name": "A", "organization": "Client One", "contact": "a@client.example"},
        {"name": "B", "organization": "Client Two", "contact": "+14155550123"},
    ],
    "authorized_contacts": [
        {
            "name": "Asha Rao",
            "designation": "Director",
            "email": "Asha@Example.com",
            "phone": "+91 98765 43210",
        }
    ],
}


def test_requires_partner_login(client: TestClient) -> None:
    assert client.get(ORG).status_code == 401


def test_profile_update_completion_and_history(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    p = onboard_partner(client, db, settings, email, org_name="Rao Systems")
    assert client.get(f"{ORG}/completion", headers=p.headers).json()["data"]["percent"] == 0
    r = client.put(
        ORG, headers=p.headers, json={"registration_number": "REG1", "year_established": 2015}
    )
    assert r.status_code == 200 and r.json()["data"]["profile_version"] == 1
    assert client.get(f"{ORG}/completion", headers=p.headers).json()["data"]["complete"] is False
    r = client.put(ORG, headers=p.headers, json=FULL)
    data = r.json()["data"]
    assert r.status_code == 200 and data["profile_version"] == 2 and data["country"] == "IN"
    meta = client.get(f"{ORG}/editable-fields", headers=p.headers).json()["data"]
    website_meta = next(item for item in meta if item["name"] == "website")
    assert website_meta["direct_update"] and website_meta["null_clears"]
    legal_name_meta = next(item for item in meta if item["name"] == "legal_name")
    assert legal_name_meta["null_clears"] is False
    comp = client.get(f"{ORG}/completion", headers=p.headers).json()["data"]
    assert comp == {"percent": 100, "missing_fields": [], "complete": True}
    hist = client.get(f"{ORG}/history", headers=p.headers).json()["data"]
    assert [h["version"] for h in hist] == [2, 1]
    assert hist[1]["changes"]["registration_number"] == {"old": None, "new": "REG1"}
    # unchanged resubmission creates no new revision
    client.put(ORG, headers=p.headers, json=FULL)
    assert len(client.get(f"{ORG}/history", headers=p.headers).json()["data"]) == 2
    cleared = client.put(ORG, headers=p.headers, json={"website": None})
    assert cleared.status_code == 200 and cleared.json()["data"]["website"] is None
    latest = client.get(f"{ORG}/history", headers=p.headers).json()["data"][0]
    assert latest["changes"]["website"]["new"] is None
    assert client.put(ORG, headers=p.headers, json={"legal_name": None}).status_code == 422


def test_validation_and_optimistic_concurrency(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    p = onboard_partner(client, db, settings, email)
    for bad in (
        {"year_established": 2999},
        {"employee_count": -1},
        {"annual_turnover_inr_crore": "-5"},
        {"website": "javascript:alert(1)"},
        {"service_categories": ["not-a-category"]},
        {"unknown_field": "x"},
        {"country": "India"},
    ):
        assert client.put(ORG, headers=p.headers, json=bad).status_code == 422, bad
    client.put(ORG, headers=p.headers, json={"registration_number": "R1"})
    stale = client.put(
        ORG, headers=p.headers, json={"registration_number": "R2", "expected_version": 0}
    )
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "PROFILE_VERSION_CONFLICT"
    body = {"registration_number": "R2", "expected_version": 1}
    ok = client.put(ORG, headers=p.headers, json=body)
    assert ok.status_code == 200


def test_organizations_are_isolated(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    a = onboard_partner(client, db, settings, email, org_name="Org A")
    b = onboard_partner(client, db, settings, email, org_name="Org B")
    client.put(ORG, headers=a.headers, json={"registration_number": "A-SECRET-REG"})
    client.put(ORG, headers=b.headers, json={"registration_number": "B-REG"})
    got_a = client.get(ORG, headers=a.headers).json()["data"]
    got_b = client.get(ORG, headers=b.headers).json()["data"]
    assert got_a["id"] == a.organization_id and got_b["id"] == b.organization_id
    assert (
        got_a["registration_number"] == "A-SECRET-REG" and got_b["registration_number"] == "B-REG"
    )
    # the organization comes only from the token: an id in the request is rejected / ignored
    assert (
        client.put(
            ORG, headers=b.headers, json={"id": a.organization_id, "legal_name": "x"}
        ).status_code
        == 422
    )
    assert (
        client.get(f"{ORG}?organization_id={a.organization_id}", headers=b.headers).json()["data"][
            "id"
        ]
        == b.organization_id
    )
    revs = db.execute(select(func.count()).select_from(PartnerProfileRevision)).scalar_one()
    assert (
        revs == 2
        and db.execute(select(func.count()).select_from(PartnerOrganization)).scalar_one() == 2
    )


def test_invitation_never_merges_organizations(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    onboard_partner(client, db, settings, email, org_name="Same Name Ltd")
    onboard_partner(client, db, settings, email, org_name="Same Name Ltd")
    names = db.execute(select(PartnerOrganization.legal_name)).scalars().all()
    assert names.count("Same Name Ltd") == 2
