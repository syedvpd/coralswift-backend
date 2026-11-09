"""Shared helpers for Phase 2 tests: staff creation, onboarding a partner through the real flow."""

import re
import uuid
from dataclasses import dataclass
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.auth.constants import StaffRole
from app.modules.auth.models import User
from app.modules.auth.service import create_staff_user
from tests.fakes import RecordingEmail

PASSWORD = "correct-horse-battery-1"
TOKEN_RE = re.compile(r"token=(cs_[A-Za-z0-9_-]+)")


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def make_staff(
    db: Session,
    settings: Settings,
    role: StaffRole = StaffRole.PARTNER_REVIEWER,
    email: str | None = None,
) -> User:
    user = create_staff_user(
        db,
        settings,
        email=email or f"staff-{uuid.uuid4().hex[:8]}@example.com",
        full_name="Staff Member",
        role=role,
        password=PASSWORD,
    )
    db.commit()
    return user


def login(client: TestClient, email: str, password: str = PASSWORD) -> dict[str, Any]:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return dict(r.json()["data"])


def last_token(email: RecordingEmail, to: str) -> str:
    for message in reversed(email.sent):
        if message.to == to:
            found = TOKEN_RE.search(message.text)
            assert found, message.text
            return found.group(1)
    raise AssertionError(f"no email to {to}")


@dataclass
class Partner:
    email: str
    organization_id: str
    headers: dict[str, str]
    tokens: dict[str, str]


def onboard_partner(
    client: TestClient,
    db: Session,
    settings: Settings,
    email_fake: RecordingEmail,
    *,
    email: str | None = None,
    org_name: str = "Rao Systems Pvt Ltd",
    admin: User | None = None,
) -> Partner:
    """Super admin invites -> email link -> partner activates -> logs in (the real flow)."""
    admin = admin or make_staff(db, settings, StaffRole.SUPER_ADMINISTRATOR)
    admin_headers = bearer(login(client, admin.email)["access_token"])
    address = email or f"partner-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post(
        "/api/v1/reviewer/invitations",
        headers=admin_headers,
        json={"email": address, "full_name": "Asha Rao", "new_organization_legal_name": org_name},
    )
    assert r.status_code == 201, r.text
    org_id = r.json()["data"]["organization_id"]
    token = last_token(email_fake, address)
    r = client.post("/api/v1/auth/invitations/accept", json={"token": token, "password": PASSWORD})
    assert r.status_code == 200, r.text
    tokens = login(client, address)
    return Partner(address, org_id, bearer(tokens["access_token"]), tokens)


FULL_PROFILE = {
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
            "email": "asha@example.com",
            "phone": "+91 98765 43210",
        }
    ],
}
REQUIRED_DOCS = (
    "registration_proof",
    "operating_history",
    "employee_strength",
    "financial_statements",
    "service_portfolio",
    "infrastructure_summary",
    "client_references",
)


def complete_partner(
    client: TestClient, partner: "Partner", *, docs: bool = True
) -> dict[str, str]:
    """Fill the profile and upload the seven required documents. Returns {category: document_id}."""
    from tests import factories

    r = client.put("/api/v1/partner/organization", headers=partner.headers, json=FULL_PROFILE)
    assert r.status_code == 200, r.text
    ids: dict[str, str] = {}
    if docs:
        for category in REQUIRED_DOCS:
            r = client.post(
                "/api/v1/partner/documents",
                headers=partner.headers,
                data={"category": category},
                files={"file": (f"{category}.pdf", factories.PDF, "application/pdf")},
            )
            assert r.status_code == 201, r.text
            ids[category] = r.json()["data"]["id"]
    return ids


def create_draft(
    client: TestClient, partner: "Partner", pathway: str = "direct_project_engagement"
) -> str:
    r = client.post(
        "/api/v1/partner/applications", headers=partner.headers, json={"pathway": pathway}
    )
    assert r.status_code == 201, r.text
    return str(r.json()["data"]["id"])


def submitted_application(client: TestClient, partner: "Partner") -> str:
    complete_partner(client, partner)
    app_id = create_draft(client, partner)
    r = client.post(f"/api/v1/partner/applications/{app_id}/submit", headers=partner.headers)
    assert r.status_code == 200, r.text
    return app_id


def staff_headers(client: TestClient, user: User) -> dict[str, str]:
    return bearer(login(client, user.email)["access_token"])
