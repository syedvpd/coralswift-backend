import logging
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.documents.models import Document
from app.modules.enquiries.models import Enquiry
from app.modules.partners.models import PartnerApplication
from app.modules.projects.models import ProjectEnquiry
from app.modules.strategic.models import StrategicEnquiry
from tests import factories
from tests.fakes import RecordingEmail

P, PA, S = (
    "/api/v1/enquiries/project",
    "/api/v1/enquiries/partner",
    "/api/v1/enquiries/strategic",
)


def upload(client: TestClient, purpose: str, category: str | None = None) -> str:
    data = {"purpose": purpose, **({"category": category} if category else {})}
    r = client.post(
        "/api/v1/documents/upload",
        data=data,
        files={"file": ("brief.pdf", factories.PDF, "application/pdf")},
    )
    assert r.status_code == 201, r.text
    return str(r.json()["data"]["document_id"])


# ---------- project ----------
@pytest.mark.parametrize("category", ["erp_implementation", "medical_coding_billing"])
def test_project_it_and_non_it(client: TestClient, db: Session, category: str) -> None:
    r = client.post(P, json=factories.project(project_category=category))
    assert r.status_code == 201
    assert db.execute(select(ProjectEnquiry.project_category)).scalar_one().value == category


@pytest.mark.parametrize(
    "override",
    [{"project_category": "casino"}, {"scope": ""}, {"geography": ""}, {"company_name": ""}],
)
def test_project_invalid(client: TestClient, override: dict[str, Any]) -> None:
    assert client.post(P, json=factories.project(**override)).status_code == 422


def test_project_missing_required(client: TestClient) -> None:
    payload = factories.project()
    del payload["requirement_summary"]
    assert client.post(P, json=payload).status_code == 422


def test_project_with_and_without_documents(client: TestClient, db: Session) -> None:
    assert client.post(P, json=factories.project()).json()["data"]["documents_attached"] == 0
    doc_id = upload(client, "project_attachment")
    r = client.post(P, json=factories.project(document_ids=[doc_id]))
    assert r.json()["data"]["documents_attached"] == 1
    doc = db.get(Document, uuid.UUID(doc_id))
    assert doc is not None and doc.owner_type.value == "enquiry" and doc.owner_id is not None
    # already attached: cannot be claimed twice
    again = client.post(P, json=factories.project(document_ids=[doc_id]))
    assert (
        again.status_code == 422 and again.json()["error"]["code"] == "INVALID_DOCUMENT_REFERENCE"
    )


def test_project_invalid_document_references(client: TestClient) -> None:
    for ref in (str(uuid.uuid4()), upload(client, "partner_evidence", "registration_proof")):
        r = client.post(P, json=factories.project(document_ids=[ref]))
        assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_DOCUMENT_REFERENCE"
    assert client.post(P, json=factories.project(document_ids=["nope"])).status_code == 422


# ---------- partner ----------
def test_partner_valid_application(client: TestClient, db: Session) -> None:
    doc_id = upload(client, "partner_evidence", "financial_statements")
    r = client.post(PA, json=factories.partner(document_ids=[doc_id]))
    assert r.status_code == 201 and r.json()["data"]["documents_attached"] == 1
    app_row = db.execute(select(PartnerApplication)).scalar_one()
    assert app_row.application_status.value == "submitted"
    assert len(app_row.client_references) == 2
    assert app_row.service_categories == ["erp", "web_applications"]
    enquiry = db.get(Enquiry, app_row.enquiry_id)
    assert enquiry is not None and enquiry.enquiry_type.value == "partner"


@pytest.mark.parametrize(
    "override",
    [
        {"preferred_engagement_pathway": "acquisition"},
        {"client_references": [{"name": "x", "organization": "y", "contact": "z"}]},
        {"year_established": 2999},
        {"service_categories": []},
        {"turnover_range": "huge"},
        {"website": "ftp://x"},
    ],
)
def test_partner_invalid(client: TestClient, override: dict[str, Any]) -> None:
    assert client.post(PA, json=factories.partner(**override)).status_code == 422


@pytest.mark.parametrize(
    "workforce, turnover, year",
    [
        ("under_50", "under_inr_2_crore", 2025),  # below every proposed threshold
        ("over_250", "over_inr_10_crore", 2000),  # above every proposed threshold
    ],
)
def test_partner_thresholds_never_decide(
    client: TestClient, db: Session, workforce: str, turnover: str, year: int
) -> None:
    r = client.post(
        PA,
        json=factories.partner(
            workforce_range=workforce, turnover_range=turnover, year_established=year
        ),
    )
    assert r.status_code == 201
    assert "approv" not in r.text.lower() and "reject" not in r.text.lower()
    assert (
        db.execute(select(PartnerApplication.application_status)).scalar_one().value == "submitted"
    )


# ---------- strategic ----------
def test_strategic_confidential_and_not_leaked(
    client: TestClient, db: Session, email: RecordingEmail, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    r = client.post(S, json=factories.strategic())
    assert r.status_code == 201
    row = db.execute(select(StrategicEnquiry)).scalar_one()
    assert row.access_classification.value == "confidential"
    enquiry = db.get(Enquiry, row.enquiry_id)
    assert enquiry is not None and enquiry.message is None  # secret text only in strategic table
    assert "TOP-SECRET-MARKER" not in caplog.text and "asha.rao@example.com" not in caplog.text
    assert all("TOP-SECRET-MARKER" not in m.text + m.html for m in email.sent)
    internal = next(m for m in email.sent if m.to == "ops-strategic@example.test")
    assert "Asha" not in internal.text  # no submitter details in the internal strategic mail


def test_strategic_requires_authorisation_and_has_no_read_api(client: TestClient) -> None:
    assert (
        client.post(S, json=factories.strategic(authorized_representative=False)).status_code == 422
    )
    paths = client.get("/openapi.json").json()["paths"]
    assert "get" not in paths[S]
    public = [
        p
        for p in paths
        if not p.startswith(("/api/v1/admin", "/api/v1/reviewer", "/api/v1/partner"))
    ]
    assert not any(
        p.endswith("/enquiries") or ("strategic" in p and "get" in paths[p]) for p in public
    )
    assert client.get("/api/v1/enquiries").status_code in (404, 405)
    assert client.get(S).status_code == 405


def test_strategic_documents_are_confidential(client: TestClient, db: Session) -> None:
    doc_id = upload(client, "strategic_attachment")
    r = client.post(S, json=factories.strategic(document_ids=[doc_id]))
    assert r.json()["data"]["documents_attached"] == 1
    assert db.execute(select(Document.classification)).scalar_one().value == "confidential"
