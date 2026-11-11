"""Extended partner profile fields and the performance foundation."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.auth.constants import StaffRole
from tests.fakes import RecordingEmail
from tests.helpers import bearer, login, make_staff, onboard_partner

P = "/api/v1/partner"
R = "/api/v1/reviewer"
ADM = "/api/v1/admin"


def _staff(client: TestClient, db: Session, settings: Settings, role: StaffRole):  # type: ignore[no-untyped-def]
    user = make_staff(db, settings, role)
    return user, bearer(login(client, user.email)["access_token"])


def test_extended_profile_fields_edit_clear_revisions_and_admin_view(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    _, sa = _staff(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    _, bdm = _staff(client, db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
    p = onboard_partner(client, db, settings, email)
    body = {
        "trading_name": "Rao Systems",
        "company_type": "private_limited",
        "state": "Telangana",
        "city": "Hyderabad",
        "primary_industry": "Logistics",
        "competencies": ["dispatch", "routing"],
        "operating_model": "hybrid",
        "coverage": ["south_india"],
        "years_of_experience": 9,
        "offices": [{"city": "Hyderabad", "country": "IN"}],
        "workforce": {"engineering": 40, "operations": 15},
        "financial_period": "FY2025-26",
        "additional_contacts": [{"name": "Ravi Kumar", "email": "ravi@example.com"}],
    }
    saved = client.put(f"{P}/organization", headers=p.headers, json=body)
    assert saved.status_code == 200, saved.text
    data = saved.json()["data"]
    assert data["trading_name"] == "Rao Systems" and data["workforce"]["engineering"] == 40
    assert data["offices"][0]["city"] == "Hyderabad" and data["years_of_experience"] == 9

    # D19: clearing an existing value is a change request; approval applies it with a revision
    direct = client.put(f"{P}/organization", headers=p.headers, json={"trading_name": None})
    assert direct.status_code == 409 and direct.json()["error"]["code"] == "CHANGE_REQUEST_REQUIRED"
    cr = client.post(
        f"{P}/organization/change-requests",
        headers=p.headers,
        json={"changes": {"trading_name": None}, "reason": "Dropped the trading name"},
    )
    assert cr.status_code == 201, cr.text
    done = client.post(
        f"{ADM}/profile-change-requests/{cr.json()['data']['id']}/decide",
        headers=sa,
        json={"approve": True},
    )
    assert done.status_code == 200, done.text
    now_org = client.get(f"{P}/organization", headers=p.headers).json()["data"]
    assert now_org["trading_name"] is None and now_org["city"] == "Hyderabad"
    history = client.get(f"{P}/organization/history", headers=p.headers).json()["data"]
    assert any(
        h["changes"].get("trading_name") == {"old": "Rao Systems", "new": None} for h in history
    )
    fields = {
        f["name"]: f
        for f in client.get(f"{P}/organization/editable-fields", headers=p.headers).json()["data"]
    }
    assert fields["trading_name"]["direct_update"] and fields["trading_name"]["approval_required"]
    assert fields["trading_name"]["null_clears"]
    assert fields["legal_name"]["null_clears"] is False

    for bad in (
        {"company_type": "corporation"},  # D44 enum
        {"operating_model": "anywhere"},
        {"years_of_experience": 500},
        {"workforce": {"engineering": -1}},
        {"offices": [{"city": "X", "bogus": 1}]},
        {"additional_contacts": [{"name": "A B", "email": "not-an-email"}]},
        {"competencies": ["x"] * 21},
    ):
        assert client.put(f"{P}/organization", headers=p.headers, json=bad).status_code == 422

    detail = client.get(f"{ADM}/organizations/{p.organization_id}", headers=sa).json()["data"][
        "profile"
    ]
    assert (
        detail["city"] == "Hyderabad" and detail["additional_contacts"][0]["name"] == "Ravi Kumar"
    )
    bdm_detail = client.get(f"{ADM}/organizations/{p.organization_id}", headers=bdm).json()["data"][
        "profile"
    ]
    assert bdm_detail["city"] == "Hyderabad" and bdm_detail.get("additional_contacts") is None
