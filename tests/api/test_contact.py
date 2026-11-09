import re
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.enquiries.models import Activity, Company, Contact, Enquiry
from app.modules.notifications.models import Notification
from tests import factories
from tests.fakes import RecordingEmail

URL = "/api/v1/enquiries/contact"
REF = re.compile(r"^CS-ENQ-\d{4}-\d{6}$")


def test_valid_submission_persists_everything(
    client: TestClient, db: Session, email: RecordingEmail
) -> None:
    r = client.post(URL, json=factories.contact())
    assert r.status_code == 201
    body = r.json()
    data = body["data"]
    assert body["success"] is True and REF.match(data["reference_number"])
    assert len(data["lookup_token"]) == 40 and data["status"] == "received"
    assert "id" not in data  # no internal IDs

    enquiry = db.execute(select(Enquiry)).scalar_one()
    contact = db.get(Contact, enquiry.contact_id)
    assert contact is not None
    assert contact.business_email == "asha.rao@example.com"  # normalised
    assert contact.phone == "+919876543210" and contact.country == "IN"
    assert contact.consent_status.value == "granted" and contact.consent_notice_version
    assert db.execute(select(func.count()).select_from(Company)).scalar_one() == 1
    assert enquiry.subject == "services" and enquiry.source == "website"
    assert db.execute(select(Activity.action)).scalars().all().count("enquiry.submitted") == 1
    # ack + one internal notification, sent after commit
    assert sorted(m.to for m in email.sent) == ["asha.rao@example.com", "ops-general@example.test"]
    ack = next(m for m in email.sent if m.to == "asha.rao@example.com")
    assert data["reference_number"] in ack.subject and "not an offer" in ack.text


def test_references_are_unique(client: TestClient) -> None:
    refs = {
        client.post(URL, json=factories.contact()).json()["data"]["reference_number"]
        for _ in range(3)
    }
    assert len(refs) == 3


@pytest.mark.parametrize(
    "override, field",
    [
        ({"full_name": ""}, "full_name"),
        ({"business_email": "not-an-email"}, "business_email"),
        ({"privacy_consent": False}, "privacy_consent"),
        ({"phone": "12345"}, "phone"),
        ({"message": "x" * 5001}, "message"),
        ({"country": "India"}, "country"),
        ({"enquiry_type": "bogus"}, "enquiry_type"),
        ({"message": "bad \x00 byte"}, "message"),
    ],
)
def test_validation_errors(client: TestClient, override: dict[str, Any], field: str) -> None:
    r = client.post(URL, json=factories.contact(**override))
    assert r.status_code == 422
    assert field in [d["field"] for d in r.json()["error"]["details"]]


def test_missing_consent_and_unknown_fields_rejected(client: TestClient) -> None:
    payload = factories.contact()
    del payload["privacy_consent"]
    assert client.post(URL, json=payload).status_code == 422
    # data minimisation: unknown fields (e.g. patient data) are refused, not stored
    assert client.post(URL, json=factories.contact(patient_record="x")).status_code == 422


def test_db_failure_rolls_back_everything_and_sends_no_email(
    client: TestClient, db: Session, email: RecordingEmail, monkeypatch: MonkeyPatch
) -> None:
    def boom(*a: object, **k: object) -> None:
        raise RuntimeError("db exploded")

    monkeypatch.setattr("app.modules.enquiries.service.queue_submission_notifications", boom)
    r = client.post(URL, json=factories.contact())
    assert r.status_code == 500 and r.json()["error"]["code"] == "INTERNAL_ERROR"
    for model in (Enquiry, Contact, Company, Notification):
        assert db.execute(select(func.count()).select_from(model)).scalar_one() == 0
    assert email.sent == []
