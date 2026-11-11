"""Comprehensive local readiness tests covering all eight public-website dependencies."""

import hashlib
import io
import uuid
import zipfile
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.integrations.botcheck import TurnstileVerifier
from app.modules.auth.constants import StaffRole
from app.modules.documents.constants import UploadStatus
from app.modules.documents.models import Document
from app.modules.engagement.models import MeetingRequest, NewsletterSubscription, PrivacyRequest
from app.modules.enquiries.models import Enquiry
from tests import factories
from tests.conftest import AppFactory
from tests.fakes import InMemoryStorage, RecordingEmail
from tests.helpers import bearer, last_token, login, make_staff, onboard_partner

APPROVED_ORIGINS = [
    "http://localhost:3000",
    "https://coralswift.com",
    "https://coralswift-ochre.vercel.app",
]

JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 16


def _xlsx_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("xl/workbook.xml", "<workbook/>")
    return buf.getvalue()


def _turnstile_mock(accepted_tokens: set[str], used_tokens: set[str]) -> TurnstileVerifier:
    def handler(request: httpx.Request) -> httpx.Response:
        body = dict(
            part.split("=", 1) for part in request.content.decode().split("&") if "=" in part
        )
        tok = body.get("response", "")
        if tok in used_tokens or tok not in accepted_tokens:
            return httpx.Response(
                200, json={"success": False, "error-codes": ["timeout-or-duplicate"]}
            )
        used_tokens.add(tok)
        return httpx.Response(200, json={"success": True, "hostname": "coralswift.com"})

    return TurnstileVerifier(
        "test-turnstile-secret",
        httpx.Client(transport=httpx.MockTransport(handler)),
        allowed_hostnames=["coralswift.com", "coralswift-ochre.vercel.app", "localhost"],
    )


def _staff_hdr(
    client: TestClient, db: Session, settings: Settings, role: StaffRole
) -> dict[str, str]:
    return bearer(login(client, make_staff(db, settings, role).email)["access_token"])


def _future_slot(days: int = 3) -> dict[str, str]:
    start = datetime.now(UTC) + timedelta(days=days)
    return {"start": start.isoformat(), "end": (start + timedelta(minutes=30)).isoformat()}


# ---------- Dependency 1: CORS configuration ----------
@pytest.mark.parametrize("origin", APPROVED_ORIGINS)
@pytest.mark.parametrize(
    ("path", "method"),
    [
        ("/api/v1/content", "GET"),
        ("/api/v1/site/contact", "GET"),
        ("/api/v1/enquiries/contact", "POST"),
        ("/api/v1/enquiries/project", "POST"),
        ("/api/v1/enquiries/partner", "POST"),
        ("/api/v1/enquiries/strategic", "POST"),
        ("/api/v1/meetings", "POST"),
        ("/api/v1/privacy/requests", "POST"),
        ("/api/v1/privacy/requests/verify", "POST"),
        ("/api/v1/documents/upload", "POST"),
        ("/api/v1/newsletter/subscribe", "POST"),
        ("/api/v1/newsletter/unsubscribe", "POST"),
    ],
)
def test_cors_approved_origins_and_preflight_headers(
    app_factory: AppFactory, origin: str, path: str, method: str
) -> None:
    app = app_factory(cors_allowed_origins=APPROVED_ORIGINS)
    with TestClient(app, raise_server_exceptions=False) as c:
        pre = c.options(
            path,
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": method,
                "Access-Control-Request-Headers": (
                    "Authorization, Content-Type, X-Bot-Token, Idempotency-Key"
                ),
            },
        )
        assert pre.status_code == 200
        assert pre.headers["access-control-allow-origin"] == origin
        assert pre.headers["access-control-allow-credentials"] == "true"
        allowed_methods = {
            m.strip().upper() for m in pre.headers["access-control-allow-methods"].split(",")
        }
        assert {"GET", "POST", "OPTIONS"}.issubset(allowed_methods)
        allowed_headers = {
            h.strip().lower() for h in pre.headers["access-control-allow-headers"].split(",")
        }
        assert {"authorization", "content-type", "x-bot-token", "idempotency-key"}.issubset(
            allowed_headers
        )


@pytest.mark.parametrize(
    "bad_origin",
    [
        "https://evil.example",
        "https://coralswift-other.vercel.app",
        "http://coralswift.com",
        "https://localhost:3000",
    ],
)
def test_cors_rejects_unapproved_origins_and_exposes_response_headers(
    app_factory: AppFactory, bad_origin: str
) -> None:
    app = app_factory(cors_allowed_origins=APPROVED_ORIGINS)
    with TestClient(app, raise_server_exceptions=False) as c:
        pre = c.options(
            "/api/v1/enquiries/contact",
            headers={
                "Origin": bad_origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type, X-Bot-Token",
            },
        )
        assert "access-control-allow-origin" not in pre.headers

        get_bad = c.get("/api/v1/site/contact", headers={"Origin": bad_origin})
        assert "access-control-allow-origin" not in get_bad.headers

        get_ok = c.get("/api/v1/site/contact", headers={"Origin": "https://coralswift.com"})
        assert get_ok.headers["access-control-allow-origin"] == "https://coralswift.com"
        assert get_ok.headers["access-control-allow-credentials"] == "true"
        exposed = {
            h.strip().lower() for h in get_ok.headers["access-control-expose-headers"].split(",")
        }
        assert {"x-request-id", "idempotent-replay", "retry-after"}.issubset(exposed)


# ---------- Dependency 2: Bot verification across all protected endpoints ----------
def test_bot_verification_enforced_and_single_use_across_all_guarded_endpoints(
    app_factory: AppFactory,
) -> None:
    used: set[str] = set()
    valid = {f"tok-{i}" for i in range(20)}
    app: FastAPI = app_factory(bot_verifier=_turnstile_mock(valid, used))
    with TestClient(app, raise_server_exceptions=False) as c:
        calls: list[tuple[str, dict[str, Any]]] = [
            ("/api/v1/enquiries/contact", {"json": factories.contact()}),
            ("/api/v1/enquiries/project", {"json": factories.project()}),
            ("/api/v1/enquiries/partner", {"json": factories.partner()}),
            ("/api/v1/enquiries/strategic", {"json": factories.strategic()}),
            (
                "/api/v1/meetings",
                {
                    "json": factories.submitter(
                        purpose="Intro call", preferred_slots=[_future_slot()], timezone="UTC"
                    )
                },
            ),
            ("/api/v1/privacy/requests", {"json": {"email": "priv@example.com", "kind": "access"}}),
            (
                "/api/v1/newsletter/subscribe",
                {"json": {"email": "news@example.com", "consent": True}},
            ),
            (
                "/api/v1/newsletter/unsubscribe",
                {"json": {"email": "news@example.com", "token": "0" * 32}},
            ),
            (
                "/api/v1/documents/upload",
                {
                    "data": {"purpose": "project_attachment"},
                    "files": {"file": ("brief.pdf", factories.PDF, "application/pdf")},
                },
            ),
        ]
        for idx, (path, kwargs) in enumerate(calls):
            missing = c.post(path, **kwargs)
            assert (
                missing.status_code == 403 and missing.json()["error"]["code"] == "BOT_CHECK_FAILED"
            )

            bad = c.post(path, headers={"X-Bot-Token": "bad-token"}, **kwargs)
            assert bad.status_code == 403 and bad.json()["error"]["code"] == "BOT_CHECK_FAILED"

            tok = f"tok-{idx}"
            good = c.post(path, headers={"X-Bot-Token": tok}, **kwargs)
            assert good.status_code != 403, (path, good.text)

            # Replaying the same single-use token fails on timeout-or-duplicate.
            reused = c.post(path, headers={"X-Bot-Token": tok}, **kwargs)
            assert (
                reused.status_code == 403 and reused.json()["error"]["code"] == "BOT_CHECK_FAILED"
            )

        # No public bot-token-issuing endpoint exists in OpenAPI.
        paths = c.get("/openapi.json").json()["paths"]
        assert not any(
            "bot" in p.lower() or "captcha" in p.lower() or "turnstile" in p.lower() for p in paths
        )


# ---------- Dependency 3: Public forms, idempotency, rate limits & confidentiality ----------
def test_all_public_submission_forms_and_idempotency_and_status_lookup(
    app_factory: AppFactory, email: RecordingEmail
) -> None:
    app = app_factory(rate_limit_per_minute=20)
    with TestClient(app, raise_server_exceptions=False) as c:
        db: Session = app.state.sessionmaker()
        try:
            endpoints: list[tuple[str, dict[str, Any], str]] = [
                ("/api/v1/enquiries/contact", factories.contact(), "general"),
                ("/api/v1/enquiries/project", factories.project(), "project"),
                ("/api/v1/enquiries/partner", factories.partner(), "partner"),
                ("/api/v1/enquiries/strategic", factories.strategic(), "strategic"),
                (
                    "/api/v1/meetings",
                    factories.submitter(
                        purpose="Discovery", preferred_slots=[_future_slot()], timezone="UTC"
                    ),
                    "meeting",
                ),
            ]
            seen_refs: set[str] = set()
            for url, payload, expected_type in endpoints:
                idem = {"Idempotency-Key": f"idem-{expected_type}-{uuid.uuid4().hex}"}
                first = c.post(url, json=payload, headers=idem)
                assert first.status_code == 201, (url, first.text)
                data = first.json()["data"]
                ref = data["reference_number"]
                assert ref not in seen_refs
                seen_refs.add(ref)
                assert data["enquiry_type"] == expected_type
                assert data["status"] == "received"

                replay = c.post(url, json=payload, headers=idem)
                assert replay.status_code == 201
                assert replay.json() == first.json()
                assert replay.headers["idempotent-replay"] == "true"

                status = c.get(
                    f"/api/v1/enquiries/{ref}/status",
                    headers={"X-Lookup-Token": data["lookup_token"]},
                )
                assert status.status_code == 200
                assert status.json()["data"]["enquiry_type"] == expected_type

            # Only one row per form (replays deduplicated); meeting stays unconfirmed.
            types = [e.enquiry_type.value for e in db.execute(select(Enquiry)).scalars()]
            assert sorted(types) == ["general", "meeting", "partner", "project", "strategic"]
            meeting = db.execute(select(MeetingRequest)).scalar_one()
            assert meeting.status.value == "requested" and meeting.calendar_checked is False
            assert any("not confirmed" in m.text.lower() for m in email.sent)

            # Strategic record hidden from BDM, visible to Super Admin.
            bdm = _staff_hdr(c, db, app.state.settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
            sa = _staff_hdr(c, db, app.state.settings, StaffRole.SUPER_ADMINISTRATOR)
            bdm_types = {
                r["enquiry_type"]
                for r in c.get("/api/v1/admin/enquiries", headers=bdm).json()["data"]
            }
            sa_types = {
                r["enquiry_type"]
                for r in c.get("/api/v1/admin/enquiries", headers=sa).json()["data"]
            }
            assert "strategic" not in bdm_types
            assert "strategic" in sa_types
        finally:
            db.close()


def test_public_forms_rate_limiting_and_attachment_failures(
    app_factory: AppFactory, storage: InMemoryStorage, email: RecordingEmail
) -> None:
    app = app_factory(rate_limit_per_minute=20)
    with TestClient(app, raise_server_exceptions=False) as c:
        db: Session = app.state.sessionmaker()
        try:
            # Failed storage upload leaves FAILED record that cannot be attached.
            storage.fail = True
            failed_up = c.post(
                "/api/v1/documents/upload",
                data={"purpose": "project_attachment"},
                files={"file": ("bad.pdf", factories.PDF, "application/pdf")},
            )
            assert failed_up.status_code == 503
            failed_doc_id = str(db.execute(select(Document.id)).scalar_one())
            assert db.get(Document, uuid.UUID(failed_doc_id)).upload_status is UploadStatus.FAILED  # type: ignore[union-attr]
            storage.fail = False

            # Failing attachment on project/partner/strategic rolls back enquiry and email.
            before_emails = len(email.sent)
            for url, body in (
                ("/api/v1/enquiries/project", factories.project(document_ids=[failed_doc_id])),
                ("/api/v1/enquiries/partner", factories.partner(document_ids=[str(uuid.uuid4())])),
                ("/api/v1/enquiries/strategic", factories.strategic(document_ids=[failed_doc_id])),
            ):
                r = c.post(url, json=body)
                assert (
                    r.status_code == 422
                    and r.json()["error"]["code"] == "INVALID_DOCUMENT_REFERENCE"
                )

            # Exceeding max_documents_per_enquiry (default 10) rejected with TOO_MANY_DOCUMENTS.
            eleven_ids: list[str] = []
            for _ in range(11):
                up = c.post(
                    "/api/v1/documents/upload",
                    data={"purpose": "project_attachment"},
                    files={"file": ("brief.pdf", factories.PDF, "application/pdf")},
                )
                assert up.status_code == 201
                eleven_ids.append(up.json()["data"]["document_id"])
            too_many = c.post(
                "/api/v1/enquiries/project", json=factories.project(document_ids=eleven_ids)
            )
            assert (
                too_many.status_code == 422
                and too_many.json()["error"]["code"] == "TOO_MANY_DOCUMENTS"
            )

            assert db.execute(select(Enquiry)).scalars().all() == []
            assert len(email.sent) == before_emails
        finally:
            db.close()

    # Meetings and privacy forms share submission rate limit.
    rl_app = app_factory(rate_limit_per_minute=2)
    with TestClient(rl_app, raise_server_exceptions=False) as c_rl:
        m_body = factories.submitter(
            purpose="Rate limit check", preferred_slots=[_future_slot()], timezone="UTC"
        )
        assert c_rl.post("/api/v1/meetings", json=m_body).status_code == 201
        assert (
            c_rl.post(
                "/api/v1/privacy/requests", json={"email": "rl@example.com", "kind": "access"}
            ).status_code
            == 201
        )
        blocked = c_rl.post("/api/v1/privacy/requests/verify", json={"token": "x" * 20})
        assert blocked.status_code == 429 and blocked.json()["error"]["code"] == "TOO_MANY_REQUESTS"


# ---------- Dependency 4: Document upload types, private storage & cross-org isolation ----------
def test_document_upload_supported_types_and_cross_org_isolation(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    uploads: list[tuple[str, bytes, str, str | None]] = [
        ("photo.jpg", JPG, "image/jpeg", "project_attachment"),
        ("img.png", factories.PNG, "image/png", "project_attachment"),
        (
            "sheet.xlsx",
            _xlsx_bytes(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "project_attachment",
        ),
        (
            "doc.docx",
            factories.docx_bytes(),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "project_attachment",
        ),
    ]
    ids: list[str] = []
    for fname, content, ctype, purpose in uploads:
        r = client.post(
            "/api/v1/documents/upload",
            data={"purpose": purpose},
            files={"file": (fname, content, ctype)},
        )
        assert r.status_code == 201, (fname, r.text)
        data = r.json()["data"]
        assert data["upload_status"] == "quarantined"
        assert data["checksum_sha256"] == hashlib.sha256(content).hexdigest()
        ids.append(data["document_id"])

    # Attach to Enquiry A; Enquiry B cannot steal those document_ids.
    ok_a = client.post("/api/v1/enquiries/project", json=factories.project(document_ids=ids))
    assert ok_a.status_code == 201 and ok_a.json()["data"]["documents_attached"] == 4
    steal_b = client.post(
        "/api/v1/enquiries/project", json=factories.project(document_ids=[ids[0]])
    )
    assert (
        steal_b.status_code == 422
        and steal_b.json()["error"]["code"] == "INVALID_DOCUMENT_REFERENCE"
    )

    # Cross-org isolation on partner portal documents + anonymous upload check.
    assert (
        client.post(
            "/api/v1/partner/documents",
            data={"category": "registration_proof"},
            files={"file": ("reg.pdf", factories.PDF, "application/pdf")},
        ).status_code
        == 401
    )
    sa = make_staff(db, settings, StaffRole.SUPER_ADMINISTRATOR)
    p1 = onboard_partner(client, db, settings, email, org_name="Org One", admin=sa)
    p2 = onboard_partner(client, db, settings, email, org_name="Org Two", admin=sa)
    p1_up = client.post(
        "/api/v1/partner/documents",
        headers=p1.headers,
        data={"category": "registration_proof"},
        files={"file": ("reg.pdf", factories.PDF, "application/pdf")},
    )
    assert p1_up.status_code == 201
    p1_doc_id = p1_up.json()["data"]["id"]
    assert (
        client.get(f"/api/v1/partner/documents/{p1_doc_id}", headers=p2.headers).status_code == 404
    )
    assert (
        client.get(
            f"/api/v1/partner/documents/{p1_doc_id}/download", headers=p2.headers
        ).status_code
        == 404
    )

    # BDM cannot download financial_statements from a partner application.
    fin_up = client.post(
        "/api/v1/documents/upload",
        data={"purpose": "partner_evidence", "category": "financial_statements"},
        files={"file": ("fin.pdf", factories.PDF, "application/pdf")},
    )
    assert fin_up.status_code == 201
    fin_doc_id = fin_up.json()["data"]["document_id"]
    pa = client.post("/api/v1/enquiries/partner", json=factories.partner(document_ids=[fin_doc_id]))
    assert pa.status_code == 201
    bdm_h = _staff_hdr(c := client, db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
    sa_h = _staff_hdr(c, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    eid = next(
        row["id"]
        for row in c.get("/api/v1/admin/enquiries?type=partner", headers=bdm_h).json()["data"]
        if row["reference_number"] == pa.json()["data"]["reference_number"]
    )
    assert (
        c.get(
            f"/api/v1/admin/enquiries/{eid}/documents/{fin_doc_id}/download", headers=bdm_h
        ).status_code
        == 404
    )
    assert (
        c.get(
            f"/api/v1/admin/enquiries/{eid}/documents/{fin_doc_id}/download", headers=sa_h
        ).status_code
        == 200
    )


# ---------- Dependency 5: Privacy verification TTL (72h), single-use, CORS & staff block ----------
def test_privacy_verification_ttl_72h_and_cors(
    app_factory: AppFactory, email: RecordingEmail
) -> None:
    app = app_factory(cors_allowed_origins=APPROVED_ORIGINS)
    with TestClient(app, raise_server_exceptions=False) as c:
        db: Session = app.state.sessionmaker()
        try:
            origin = "https://coralswift-ochre.vercel.app"
            sub = c.post(
                "/api/v1/privacy/requests",
                headers={"Origin": origin},
                json={
                    "email": "verify72@example.com",
                    "kind": "access",
                    "details": "Export my data",
                },
            )
            assert sub.status_code == 201
            assert sub.headers["access-control-allow-origin"] == origin
            ref = sub.json()["data"]["reference"]

            row = db.execute(
                select(PrivacyRequest).where(PrivacyRequest.reference == ref)
            ).scalar_one()
            assert row.email_verified_at is None
            assert row.verification_expires_at is not None
            ttl_hours = (row.verification_expires_at - row.created_at).total_seconds() / 3600
            assert 71.9 <= ttl_hours <= 72.1

            tok = last_token(email, "verify72@example.com")
            mail_text = next(m.text for m in email.sent if m.to == "verify72@example.com")
            assert "/privacy/verify?token=" in mail_text

            # Expired at exact 72h mark is refused.
            db.execute(
                update(PrivacyRequest)
                .where(PrivacyRequest.id == row.id)
                .values(verification_expires_at=row.created_at - timedelta(seconds=1))
            )
            db.commit()
            expired = c.post(
                "/api/v1/privacy/requests/verify",
                headers={"Origin": origin},
                json={"token": tok},
            )
            assert expired.status_code == 400 and expired.json()["error"]["code"] == "TOKEN_EXPIRED"

            # Restore expiry -> single-use verification succeeds over CORS.
            db.execute(
                update(PrivacyRequest)
                .where(PrivacyRequest.id == row.id)
                .values(verification_expires_at=row.created_at + timedelta(hours=72))
            )
            db.commit()
            ok_v = c.post(
                "/api/v1/privacy/requests/verify",
                headers={"Origin": origin},
                json={"token": tok},
            )
            assert ok_v.status_code == 200 and ok_v.json()["data"]["reference"] == ref
            assert ok_v.headers["access-control-allow-origin"] == origin
            reuse = c.post("/api/v1/privacy/requests/verify", json={"token": tok})
            assert (
                reuse.status_code == 400
                and reuse.json()["error"]["code"] == "INVALID_OR_EXPIRED_TOKEN"
            )
        finally:
            db.close()


# ---------- Dependency 6: Insights CMS & SEO schema (?type=article) ----------
def test_insights_articles_seo_schema_and_filtering(
    client: TestClient, db: Session, settings: Settings
) -> None:
    # Verify local migrated schema actually contains the 8 SEO columns from migration 0013.
    cols = {col["name"] for col in inspect(db.bind).get_columns("content_items")}
    expected_seo_cols = {
        "seo_title",
        "seo_description",
        "canonical_url",
        "og_title",
        "og_description",
        "og_image_url",
        "image_url",
        "image_alt",
    }
    assert expected_seo_cols.issubset(cols)

    # Empty article list.
    empty = client.get("/api/v1/content?type=article")
    assert empty.status_code == 200
    assert empty.json()["data"] == [] and empty.json()["meta"]["total"] == 0

    # Invalid content type -> 422.
    assert client.get("/api/v1/content?type=bogus").status_code == 422

    ca = _staff_hdr(client, db, settings, StaffRole.CONTENT_ADMINISTRATOR)
    sa = _staff_hdr(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    ac = "/api/v1/admin/content"

    # Draft article (never visible publicly) + published page (filtered out by type=article).
    client.post(
        ac,
        headers=ca,
        json={
            "slug": "draft-insight",
            "content_type": "article",
            "title": "Draft",
            "body": "Draft body",
        },
    )
    page_id = client.post(
        ac,
        headers=ca,
        json={"slug": "about-us", "content_type": "page", "title": "About", "body": "About body"},
    ).json()["data"]["id"]
    client.post(f"{ac}/{page_id}/submit", headers=ca)
    client.post(f"{ac}/{page_id}/approve", headers=sa, json={})
    client.post(f"{ac}/{page_id}/publish", headers=ca)

    # Published article WITHOUT optional SEO fields.
    plain_id = client.post(
        ac,
        headers=ca,
        json={
            "slug": "plain-insight",
            "content_type": "article",
            "title": "Plain Insight",
            "body": "Body",
        },
    ).json()["data"]["id"]
    client.post(f"{ac}/{plain_id}/submit", headers=ca)
    client.post(f"{ac}/{plain_id}/approve", headers=sa, json={})
    client.post(f"{ac}/{plain_id}/publish", headers=ca)

    # Published article WITH full SEO metadata.
    full_seo = {
        "seo_title": "Delivery Playbook SEO",
        "seo_description": "Enterprise delivery insights.",
        "canonical_url": "https://coralswift.com/insights/playbook",
        "og_title": "Delivery Playbook OG",
        "og_description": "Read the playbook.",
        "og_image_url": "https://cdn.coralswift.com/og.png",
        "image_url": "https://cdn.coralswift.com/cover.jpg",
        "image_alt": "Playbook cover",
    }
    seo_id = client.post(
        ac,
        headers=ca,
        json={
            "slug": "delivery-playbook",
            "content_type": "article",
            "title": "Delivery Playbook",
            "summary": "Summary here",
            "body": "Article body text",
            "category": "engineering",
            "tags": ["delivery"],
            **full_seo,
        },
    ).json()["data"]["id"]
    client.post(f"{ac}/{seo_id}/submit", headers=ca)
    client.post(f"{ac}/{seo_id}/approve", headers=sa, json={})
    client.post(f"{ac}/{seo_id}/publish", headers=ca)

    res = client.get("/api/v1/content?type=article")
    assert res.status_code == 200
    assert res.headers["cache-control"] == "public, max-age=300"
    items = res.json()["data"]
    slugs = {i["slug"]: i for i in items}
    assert set(slugs) == {"plain-insight", "delivery-playbook"}
    assert "draft-insight" not in slugs and "about-us" not in slugs
    for k, v in full_seo.items():
        assert slugs["delivery-playbook"][k] == v
    for k in expected_seo_cols:
        assert slugs["plain-insight"][k] is None


# ---------- Dependency 7: Corporate contact information ----------
def test_site_contact_empty_and_populated(
    client: TestClient, db: Session, settings: Settings
) -> None:
    empty = client.get("/api/v1/site/contact")
    assert empty.status_code == 200
    assert empty.json()["data"] == {}
    assert empty.headers["cache-control"] == "public, max-age=300"

    sa = _staff_hdr(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    pairs = {
        "domain": "coralswift.com",
        "email": "contact@coralswift.com",
        "address": "Suite 100, Example Park, Bengaluru",
        "phone": "+91 80 1234 5678",
        "representative": "Authorized Signatory",
    }
    for key, value in pairs.items():
        r = client.put(f"/api/v1/admin/settings/contact.{key}", headers=sa, json={"value": value})
        assert r.status_code == 200, (key, r.text)

    populated = client.get("/api/v1/site/contact")
    assert populated.status_code == 200
    assert populated.json()["data"] == {
        **pairs,
        "phone": "+918012345678",  # normalized to E.164
    }


# ---------- Dependency 8: Newsletter workflow & HMAC unsubscribe security ----------
def test_newsletter_complete_workflow_and_token_security(
    client: TestClient, db: Session, settings: Settings
) -> None:
    assert (
        client.post(
            "/api/v1/newsletter/subscribe", json={"email": "n@example.com", "consent": False}
        ).status_code
        == 422
    )
    sub1 = client.post(
        "/api/v1/newsletter/subscribe", json={"email": "Reader@Example.com", "consent": True}
    )
    assert sub1.status_code == 200
    tok1 = sub1.json()["data"]["unsubscribe_token"]
    assert len(tok1) == 32

    sub2 = client.post(
        "/api/v1/newsletter/subscribe", json={"email": "other@example.com", "consent": True}
    )
    tok2 = sub2.json()["data"]["unsubscribe_token"]
    assert tok1 != tok2

    # Token from user 2 cannot unsubscribe user 1.
    cross = client.post(
        "/api/v1/newsletter/unsubscribe", json={"email": "reader@example.com", "token": tok2}
    )
    assert cross.status_code == 404

    ok_unsub = client.post(
        "/api/v1/newsletter/unsubscribe", json={"email": "reader@example.com", "token": tok1}
    )
    assert ok_unsub.status_code == 200 and ok_unsub.json()["data"] is None
    row = db.execute(
        select(NewsletterSubscription).where(NewsletterSubscription.email == "reader@example.com")
    ).scalar_one()
    assert row.status.value == "unsubscribed" and row.unsubscribed_at is not None

    # Idempotent unsubscribe and re-subscribe both succeed.
    assert (
        client.post(
            "/api/v1/newsletter/unsubscribe", json={"email": "reader@example.com", "token": tok1}
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/newsletter/subscribe", json={"email": "reader@example.com", "consent": True}
        ).status_code
        == 200
    )
    db.refresh(row)
    assert row.status.value == "subscribed" and row.unsubscribed_at is None

    # Super admin CSV export; non-super denied.
    bdm = _staff_hdr(client, db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
    sa = _staff_hdr(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    assert client.get("/api/v1/admin/reports/newsletter.csv", headers=bdm).status_code == 403
    csv_res = client.get("/api/v1/admin/reports/newsletter.csv", headers=sa)
    assert csv_res.status_code == 200
    assert "reader@example.com" in csv_res.text and "other@example.com" in csv_res.text
