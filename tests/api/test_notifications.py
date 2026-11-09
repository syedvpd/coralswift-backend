import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.enquiries.constants import EnquiryType
from app.modules.enquiries.models import Activity, Enquiry
from app.modules.notifications.constants import DeliveryStatus, TemplateKey
from app.modules.notifications.models import Notification
from app.modules.notifications.service import dispatch_notifications, queue_submission_notifications
from app.modules.notifications.templates import render
from tests import factories
from tests.fakes import RecordingEmail

URL = "/api/v1/enquiries/contact"


def rows(db: Session) -> list[Notification]:
    db.expire_all()
    return list(db.execute(select(Notification).order_by(Notification.created_at)).scalars())


def test_templates_render_html_and_text_with_escaping() -> None:
    for key in TemplateKey:
        subject, text, html = render(
            key,
            {"reference": "CS-ENQ-2026-000001", "enquiry_type": "partner", "name": "<b>Eve</b>"},
        )
        assert html.startswith("<html>") and subject
        if key not in (
            TemplateKey.PARTNER_INVITATION,
            TemplateKey.PASSWORD_RESET,
            TemplateKey.EXPIRY_REMINDER,
            TemplateKey.PROFILE_CHANGE_DECISION,
        ):
            assert "CS-ENQ-2026-000001" in subject + text
    _, text, html = render(TemplateKey.ACK_GENERAL, {"reference": "R", "name": "<b>Eve</b>"})
    assert "<b>Eve</b>" in text and "&lt;b&gt;Eve&lt;/b&gt;" in html and "<b>" not in html
    assert "within" not in text.lower() and "hours" not in text.lower()  # no invented SLA


def test_ack_template_chosen_per_type(client: TestClient, db: Session) -> None:
    client.post(URL, json=factories.contact())
    keys = {n.template_key for n in rows(db)}
    assert keys == {TemplateKey.ACK_GENERAL, TemplateKey.INTERNAL_NEW_ENQUIRY}


def test_provider_failure_then_retry_succeeds_once(
    app: FastAPI, client: TestClient, db: Session, email: RecordingEmail, settings: Settings
) -> None:
    email.fail = True
    r = client.post(URL, json=factories.contact())
    assert r.status_code == 201  # the submission itself is not lost
    assert {n.delivery_status for n in rows(db)} == {DeliveryStatus.FAILED}
    assert all(n.retry_count == 1 and n.last_error for n in rows(db))
    assert "notification.failed" in set(db.execute(select(Activity.action)).scalars())

    email.fail = False
    done = dispatch_notifications(app.state.sessionmaker, email, settings)
    assert done == 2 and len(email.sent) == 2
    assert {n.delivery_status for n in rows(db)} == {DeliveryStatus.SENT}
    # running again sends nothing: no duplicates
    assert dispatch_notifications(app.state.sessionmaker, email, settings) == 0
    assert len(email.sent) == 2


def test_retry_cap(
    app: FastAPI, client: TestClient, db: Session, email: RecordingEmail, settings: Settings
) -> None:
    email.fail = True
    client.post(URL, json=factories.contact())
    for _ in range(10):
        dispatch_notifications(app.state.sessionmaker, email, settings)
    assert all(n.retry_count == settings.notification_max_retries for n in rows(db))


def test_console_style_backend_is_logged_not_sent(
    client: TestClient, db: Session, email: RecordingEmail
) -> None:
    email.delivered = False
    client.post(URL, json=factories.contact())
    assert {n.delivery_status for n in rows(db)} == {DeliveryStatus.LOGGED}


def test_queueing_twice_creates_no_duplicates(db: Session, settings: Settings) -> None:
    contact_enquiry = factories.contact()
    # build a real enquiry through the service to get valid FKs
    from app.modules.enquiries.schemas import ContactEnquiryIn
    from app.modules.enquiries.service import create_contact_enquiry

    created = create_contact_enquiry(db, settings, ContactEnquiryIn(**contact_enquiry))
    before = len(rows(db))
    queue_submission_notifications(
        db,
        settings,
        enquiry_id=created.enquiry.id,
        enquiry_type=EnquiryType.GENERAL,
        reference=created.out.reference_number,
        submitter_email=created.contact.business_email,
        submitter_name="x",
        company=None,
    )
    assert len(rows(db)) == before
    assert isinstance(created.enquiry, Enquiry) and isinstance(created.enquiry.id, uuid.UUID)
