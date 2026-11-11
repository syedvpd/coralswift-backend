"""CMS blocks and media library, audit origin/outcome columns."""

from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.auth.constants import StaffRole
from tests import factories
from tests.conftest import AppFactory
from tests.fakes import RecordingEmail
from tests.helpers import bearer, login, make_staff

ADM = "/api/v1/admin"
PUBLIC = "/api/v1"
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6360000002000001e221bc330000000049454e44ae426082"
)


def _staff(client: TestClient, db: Session, settings: Settings, role: StaffRole):  # type: ignore[no-untyped-def]
    user = make_staff(db, settings, role)
    return user, bearer(login(client, user.email)["access_token"])


def _publish(client: TestClient, sa: dict[str, str], ca: dict[str, str], payload: dict) -> str:  # type: ignore[type-arg]
    r = client.post(f"{ADM}/content", headers=ca, json=payload)
    assert r.status_code == 201, r.text
    cid = r.json()["data"]["id"]
    for step, who in (("submit", ca), ("approve", sa), ("publish", ca)):
        res = client.post(f"{ADM}/content/{cid}/{step}", headers=who, json={})
        assert res.status_code == 200, (step, res.text)
    return str(cid)


def test_cms_blocks_navigation_validation_markdown_and_editor(
    client: TestClient, db: Session, settings: Settings
) -> None:
    _, sa = _staff(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    editor, ca = _staff(client, db, settings, StaffRole.CONTENT_ADMINISTRATOR)
    nav = {
        "slug": "main-menu",
        "content_type": "navigation",
        "title": "Main menu",
        "body": "Primary navigation",
        "data": {"items": [{"label": "Services", "url": "/services", "children": []}]},
    }
    for bad in (
        {"items": [{"label": "x", "url": "javascript:alert(1)"}]},
        {"items": [{"label": "x", "url": "//evil.example"}]},
        {"items": "nope"},
        {"items": [{"label": "x", "url": "/ok", "extra": 1}]},
    ):
        r = client.post(f"{ADM}/content", headers=ca, json={**nav, "data": bad})
        assert r.status_code == 422, bad
    html = client.post(f"{ADM}/content", headers=ca, json={**nav, "body_format": "html"})
    assert html.status_code == 422

    cid = _publish(client, sa, ca, nav)
    live = client.get(f"{PUBLIC}/content/main-menu").json()["data"]
    assert live["content_type"] == "navigation" and live["data"]["items"][0]["url"] == "/services"
    admin_row = client.get(f"{ADM}/content/{cid}", headers=ca).json()["data"]
    assert admin_row["updated_by"] == str(editor.id) and admin_row["updated_at"]

    hero = client.post(
        f"{ADM}/content",
        headers=ca,
        json={
            "slug": "home-hero",
            "content_type": "hero",
            "title": "Hero",
            "body": "**Delivery** excellence",
            "body_format": "markdown",
            "data": {"cta_label": "Contact us", "cta_url": "/contact"},
        },
    )
    assert hero.status_code == 201 and hero.json()["data"]["body_format"] == "markdown"
    hid = hero.json()["data"]["id"]
    bad_update = client.patch(
        f"{ADM}/content/{hid}", headers=ca, json={"data": {"x": "y" * 30_000}}
    )
    assert (
        bad_update.status_code == 409 and bad_update.json()["error"]["code"] == "INVALID_BLOCK_DATA"
    )
    listing = client.get(f"{PUBLIC}/content?type=navigation").json()
    assert [i["slug"] for i in listing["data"]] == ["main-menu"]


def test_media_library_upload_publish_and_public_serving(
    client: TestClient, db: Session, settings: Settings
) -> None:
    _, ca = _staff(client, db, settings, StaffRole.CONTENT_ADMINISTRATOR)
    _, bdm = _staff(client, db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
    up = client.post(
        f"{ADM}/media", headers=ca, data={"alt_text": "Team"}, files={"file": ("team.png", PNG)}
    )
    assert up.status_code == 201, up.text
    media = up.json()["data"]
    assert media["is_public"] is False and media["public_url_path"] is None
    mid = media["id"]

    pdf = client.post(f"{ADM}/media", headers=ca, files={"file": ("doc.pdf", factories.PDF)})
    assert pdf.status_code == 415 and pdf.json()["error"]["code"] == "NOT_AN_IMAGE"
    fake = client.post(f"{ADM}/media", headers=ca, files={"file": ("fake.png", b"not an image")})
    assert fake.status_code in (415, 422)
    assert (
        client.post(f"{ADM}/media", headers=bdm, files={"file": ("a.png", PNG)}).status_code == 403
    )
    assert client.get(f"{ADM}/media").status_code == 401

    assert client.get(f"/api/v1/media/{mid}/file").status_code == 404  # not published yet
    assert client.get(f"{ADM}/media/{mid}/file", headers=ca).content == PNG
    pub = client.post(f"{ADM}/media/{mid}/publish", headers=ca)
    assert pub.json()["data"]["public_url_path"] == f"/media/{mid}/file"
    served = client.get(f"/api/v1/media/{mid}/file")
    assert served.status_code == 200 and served.content == PNG
    assert served.headers["content-type"] == "image/png"
    assert served.headers["x-content-type-options"] == "nosniff"

    assert client.get(f"{ADM}/media?published=true", headers=ca).json()["meta"]["total"] == 1
    assert client.post(f"{ADM}/media/{mid}/archive", headers=ca).status_code == 200
    assert client.get(f"/api/v1/media/{mid}/file").status_code == 404
    assert client.post(f"{ADM}/media/{mid}/publish", headers=ca).status_code == 409
    assert client.get(f"{ADM}/media?archived=true", headers=ca).json()["meta"]["total"] == 1


def test_audit_rows_record_origin_and_outcome(
    client: TestClient, db: Session, settings: Settings
) -> None:
    sa_user, sa = _staff(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    victim = make_staff(db, settings, StaffRole.PARTNER_REVIEWER)
    bad = client.post(
        "/api/v1/auth/login",
        json={"email": victim.email, "password": "wrong-password-123"},
        headers={"User-Agent": "audit-test-agent/1.0"},
    )
    assert bad.status_code == 401
    rows = client.get(f"{ADM}/audit?action=auth.login_failed", headers=sa).json()["data"]
    failed = [r for r in rows if r["actor_user_id"] == str(victim.id)]
    assert failed and failed[0]["outcome"] == "failure"
    assert failed[0]["user_agent"] == "audit-test-agent/1.0" and failed[0]["ip_address"]
    ok_rows = client.get(f"{ADM}/audit?action=auth.login", headers=sa).json()["data"]
    assert any(r["actor_user_id"] == str(sa_user.id) and r["outcome"] == "success" for r in ok_rows)
    csv = client.get(f"{ADM}/audit.csv", headers=sa).text.splitlines()[0]
    assert "ip_address" in csv and "outcome" in csv
    # only super administrators can read origin data
    _, bdm = _staff(client, db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
    assert client.get(f"{ADM}/audit", headers=bdm).status_code == 403


def test_bounce_webhook_disabled_without_secret_and_marks_bounced(
    app_factory: AppFactory, settings: Settings
) -> None:
    from sqlalchemy import select

    from app.modules.notifications.constants import DeliveryStatus
    from app.modules.notifications.models import Notification

    off = app_factory()
    with TestClient(off, raise_server_exceptions=False) as c:
        body = {"event": "hard_bounce", "email": "x@example.com"}
        assert c.post("/api/v1/webhooks/email", json=body).status_code == 404

    on = app_factory(email_webhook_secret=SecretStr("s" * 40))
    with TestClient(on, raise_server_exceptions=False) as c:
        db: Session = on.state.sessionmaker()
        db.add(
            Notification(
                recipient="bounce@example.com",
                notification_type="reply",
                template_key="staff_reply",
                context={},
                delivery_status=DeliveryStatus.SENT,
                retry_count=0,
                dedupe_key="bounce-test-1",
            )
        )
        db.commit()
        body = {"event": "hard_bounce", "email": "Bounce@Example.com"}
        assert c.post("/api/v1/webhooks/email", json=body).status_code == 401
        bad = c.post("/api/v1/webhooks/email", json=body, headers={"X-Webhook-Secret": "nope"})
        assert bad.status_code == 401
        good = c.post("/api/v1/webhooks/email", json=body, headers={"X-Webhook-Secret": "s" * 40})
        assert good.status_code == 200 and good.json()["data"]["updated"] == 1
        db.expire_all()
        row = db.execute(
            select(Notification).where(Notification.dedupe_key == "bounce-test-1")
        ).scalar_one()
        assert row.delivery_status is DeliveryStatus.BOUNCED


def test_purge_requires_removed_document_ended_retention_and_super_admin(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    from datetime import timedelta

    from sqlalchemy import update

    from app.common.utilities import utcnow
    from app.modules.partner_documents.models import PartnerDocumentVersion
    from tests.helpers import onboard_partner

    _, sa = _staff(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    _, rev = _staff(client, db, settings, StaffRole.PARTNER_REVIEWER)
    p = onboard_partner(client, db, settings, email)
    up = client.post(
        "/api/v1/partner/documents",
        headers=p.headers,
        data={"category": "registration_proof"},
        files={"file": ("a.pdf", factories.PDF)},
    )
    doc_id = up.json()["data"]["id"]
    url = f"{ADM}/documents/{doc_id}/purge"
    body = {"reason": "Retention ended, legal check recorded"}
    assert client.post(url, headers=rev, json=body).status_code == 403
    blocked = client.post(url, headers=sa, json=body)
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "RETENTION_POLICY_NOT_APPROVED"
    # legal sign-off recorded: the retention setting exists (value is the owner's decision)
    assert (
        client.put(
            f"{ADM}/settings/retention.partner_document_days", headers=sa, json={"value": "3650"}
        ).status_code
        == 200
    )
    live = client.post(url, headers=sa, json=body)
    assert live.status_code == 409 and live.json()["error"]["code"] == "NOT_REMOVED"
    assert client.delete(f"/api/v1/partner/documents/{doc_id}", headers=p.headers).status_code in (
        200,
        204,
    )
    early = client.post(url, headers=sa, json=body)
    assert early.status_code == 409 and early.json()["error"]["code"] == "RETENTION_ACTIVE"
    db.execute(update(PartnerDocumentVersion).values(retention_date=utcnow() - timedelta(days=1)))
    db.commit()
    assert client.post(url, headers=sa, json={}).status_code == 422
    done = client.post(url, headers=sa, json=body)
    assert done.status_code == 200 and done.json()["data"]["versions_purged"] >= 1
    again = client.post(url, headers=sa, json=body)
    assert again.json()["data"]["versions_purged"] == 0
    audit = client.get(f"{ADM}/audit?action=document.purged_by_staff", headers=sa).json()
    assert audit["meta"]["total"] == 2 and audit["data"][0]["actor_type"] == "staff"
