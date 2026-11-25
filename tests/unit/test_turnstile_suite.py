"""Comprehensive Turnstile Bot Protection & Siteverify Test Suite.

Covers:
- Valid token verification with secret forwarding
- Invalid token rejection
- Missing and whitespace token rejection (no provider call)
- Oversized token rejection (>2048 chars, no provider call)
- Expired token rejection
- Replayed token rejection (timeout-or-duplicate)
- Wrong hostname rejection and case-insensitive matching
- Expected action validation (matching and mismatched action)
- Siteverify timeout fail-closed
- Cloudflare unavailable fail-closed (500, 502, 503, ConnectError)
- Malformed response fail-closed (non-JSON, non-dict, missing success, non-boolean success)
- Cloudflare official test keys behavior
- All protected public endpoints rejection on missing/invalid token
- Safe unauthenticated endpoints that do not require X-Bot-Token
"""

from collections.abc import Callable

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.integrations.botcheck import (
    DEFAULT_TIMEOUT_SECONDS,
    MAX_TOKEN_LENGTH,
    NoopBotVerifier,
    TurnstileVerifier,
    build_bot_verifier,
)
from app.main import create_app
from tests.fakes import InMemoryStorage, RecordingEmail

# Official Cloudflare Turnstile Test Keys (documented by Cloudflare for testing)
CLOUDFLARE_TEST_SITEKEY_PASS = "1x00000000000000000000AA"
CLOUDFLARE_TEST_SECRET_PASS = "1x0000000000000000000000000000000AA"
CLOUDFLARE_TEST_SITEKEY_FAIL = "2x00000000000000000000AB"
CLOUDFLARE_TEST_SECRET_FAIL = "2x0000000000000000000000000000000AB"


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    """Override database migration fixture for isolated unit testing."""
    return None


DEFAULT_TEST_SECRET = "test-secret-key"  # noqa: S105


def _make_verifier(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    secret: str = DEFAULT_TEST_SECRET,
    allowed_hostnames: list[str] | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> TurnstileVerifier:
    return TurnstileVerifier(
        secret,
        httpx.Client(transport=httpx.MockTransport(handler)),
        allowed_hostnames=allowed_hostnames,
        timeout_seconds=timeout_seconds,
    )


# ---------------------------------------------------------------------------
# 1. Valid Token & Secret Forwarding
# ---------------------------------------------------------------------------
def test_valid_token_success() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.content.decode()
        return httpx.Response(
            200,
            json={
                "success": True,
                "challenge_ts": "2026-11-24T10:00:00.000Z",
                "hostname": "coralswift.com",
            },
        )

    verifier = _make_verifier(handler, secret="turnstile-backend-secret")
    result = verifier.verify("valid-fresh-token", "203.0.113.1")
    assert result is True
    assert "secret=turnstile-backend-secret" in seen["body"]
    assert "response=valid-fresh-token" in seen["body"]
    assert "remoteip=203.0.113.1" in seen["body"]


# ---------------------------------------------------------------------------
# 2. Invalid Token Rejection
# ---------------------------------------------------------------------------
def test_invalid_token_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"success": False, "error-codes": ["invalid-input-response"]},
        )

    verifier = _make_verifier(handler)
    assert verifier.verify("bogus-token", "1.2.3.4") is False


# ---------------------------------------------------------------------------
# 3. Missing, Empty, and Oversized Tokens (Skipping Provider Call)
# ---------------------------------------------------------------------------
def test_missing_and_empty_tokens_skip_provider_call() -> None:
    called = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal called
        called += 1
        return httpx.Response(200, json={"success": True})

    verifier = _make_verifier(handler)
    assert verifier.verify(None, "1.2.3.4") is False
    assert verifier.verify("", "1.2.3.4") is False
    assert verifier.verify("   ", "1.2.3.4") is False
    assert verifier.verify("\t\n  ", "1.2.3.4") is False
    assert called == 0


def test_oversized_token_rejected_without_provider_call() -> None:
    called = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal called
        called += 1
        return httpx.Response(200, json={"success": True})

    verifier = _make_verifier(handler)
    oversized = "a" * (MAX_TOKEN_LENGTH + 1)
    assert verifier.verify(oversized, "1.2.3.4") is False
    assert called == 0

    # Token within limit is processed
    within_limit = "a" * MAX_TOKEN_LENGTH
    assert verifier.verify(within_limit, "1.2.3.4") is True
    assert called == 1


# ---------------------------------------------------------------------------
# 4. Expired Token
# ---------------------------------------------------------------------------
def test_expired_token_rejected() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"success": False, "error-codes": ["timeout-or-duplicate"]},
        )

    verifier = _make_verifier(handler)
    assert verifier.verify("expired-token", "1.2.3.4") is False


# ---------------------------------------------------------------------------
# 5. Replayed Token Rejection
# ---------------------------------------------------------------------------
def test_replayed_token_rejected() -> None:
    used_tokens: set[str] = set()

    def handler(request: httpx.Request) -> httpx.Response:
        body = dict(
            part.split("=", 1) for part in request.content.decode().split("&") if "=" in part
        )
        tok = body.get("response", "")
        if tok in used_tokens:
            return httpx.Response(
                200,
                json={"success": False, "error-codes": ["timeout-or-duplicate"]},
            )
        used_tokens.add(tok)
        return httpx.Response(200, json={"success": True, "hostname": "coralswift.com"})

    verifier = _make_verifier(handler, allowed_hostnames=["coralswift.com"])
    token = "single-use-turnstile-token"

    # First submission succeeds
    assert verifier.verify(token, "1.2.3.4") is True

    # Immediate replay of the exact same token fails
    assert verifier.verify(token, "1.2.3.4") is False


# ---------------------------------------------------------------------------
# 6. Hostname Validation
# ---------------------------------------------------------------------------
def test_hostname_allowed_and_case_insensitive() -> None:
    verifier = _make_verifier(
        lambda _: httpx.Response(200, json={"success": True, "hostname": "CoralSwift.Com"}),
        allowed_hostnames=["coralswift.com", "coral-swift.vercel.app"],
    )
    assert verifier.verify("tok", "1.2.3.4") is True


def test_wrong_hostname_rejected() -> None:
    verifier = _make_verifier(
        lambda _: httpx.Response(200, json={"success": True, "hostname": "attacker-domain.com"}),
        allowed_hostnames=["coralswift.com", "coral-swift.vercel.app"],
    )
    assert verifier.verify("tok", "1.2.3.4") is False


def test_missing_hostname_rejected_when_hostnames_configured() -> None:
    verifier = _make_verifier(
        lambda _: httpx.Response(200, json={"success": True}),
        allowed_hostnames=["coralswift.com"],
    )
    assert verifier.verify("tok", "1.2.3.4") is False


# ---------------------------------------------------------------------------
# 7. Action Validation
# ---------------------------------------------------------------------------
def test_action_validation_matching() -> None:
    verifier = _make_verifier(
        lambda _: httpx.Response(200, json={"success": True, "action": "contact_submit"}),
    )
    assert verifier.verify("tok", "1.2.3.4", expected_action="contact_submit") is True


def test_action_validation_mismatched_rejected() -> None:
    verifier = _make_verifier(
        lambda _: httpx.Response(200, json={"success": True, "action": "newsletter_subscribe"}),
    )
    assert verifier.verify("tok", "1.2.3.4", expected_action="contact_submit") is False


def test_action_validation_missing_action_rejected() -> None:
    verifier = _make_verifier(
        lambda _: httpx.Response(200, json={"success": True}),
    )
    assert verifier.verify("tok", "1.2.3.4", expected_action="contact_submit") is False


# ---------------------------------------------------------------------------
# 8. Timeout & Network Errors (Fail Closed)
# ---------------------------------------------------------------------------
def test_siteverify_timeout_fails_closed() -> None:
    def timeout_handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Cloudflare siteverify timed out")

    verifier = _make_verifier(timeout_handler)
    assert verifier.verify("tok", "1.2.3.4") is False


def test_cloudflare_unavailable_fails_closed() -> None:
    def connect_error_handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused by provider")

    assert _make_verifier(connect_error_handler).verify("tok", "1.2.3.4") is False

    for status in (500, 502, 503, 504):
        assert (
            _make_verifier(lambda _, s=status: httpx.Response(s)).verify("tok", "1.2.3.4") is False
        )


# ---------------------------------------------------------------------------
# 9. Malformed Responses (Fail Closed)
# ---------------------------------------------------------------------------
def test_malformed_responses_fail_closed() -> None:
    # Non-JSON HTML error page
    assert (
        _make_verifier(lambda _: httpx.Response(200, content=b"<html>Bad Gateway</html>")).verify(
            "tok", "ip"
        )
        is False
    )

    # JSON that is not a dictionary (e.g. list, integer, string)
    assert (
        _make_verifier(lambda _: httpx.Response(200, json=["invalid"])).verify("tok", "ip") is False
    )
    assert _make_verifier(lambda _: httpx.Response(200, json="true")).verify("tok", "ip") is False
    assert _make_verifier(lambda _: httpx.Response(200, json=123)).verify("tok", "ip") is False

    # Success key has truthy string instead of boolean True
    assert (
        _make_verifier(lambda _: httpx.Response(200, json={"success": "true"})).verify("tok", "ip")
        is False
    )
    assert (
        _make_verifier(lambda _: httpx.Response(200, json={"success": 1})).verify("tok", "ip")
        is False
    )
    assert (
        _make_verifier(lambda _: httpx.Response(200, json={"success": None})).verify("tok", "ip")
        is False
    )


# ---------------------------------------------------------------------------
# 10. Cloudflare Documented Test Keys Behavior
# ---------------------------------------------------------------------------
def test_cloudflare_documented_test_keys_simulation() -> None:
    """Verifies standard test keys behave correctly under simulated test environments."""

    def test_key_handler(request: httpx.Request) -> httpx.Response:
        content = request.content.decode()
        if f"secret={CLOUDFLARE_TEST_SECRET_PASS}" in content:
            return httpx.Response(200, json={"success": True, "hostname": "localhost"})
        return httpx.Response(200, json={"success": False, "error-codes": ["invalid-input-secret"]})

    pass_verifier = _make_verifier(test_key_handler, secret=CLOUDFLARE_TEST_SECRET_PASS)
    fail_verifier = _make_verifier(test_key_handler, secret=CLOUDFLARE_TEST_SECRET_FAIL)

    assert pass_verifier.verify("dummy-token", "127.0.0.1") is True
    assert fail_verifier.verify("dummy-token", "127.0.0.1") is False


# ---------------------------------------------------------------------------
# 11. NoopBotVerifier Behavior
# ---------------------------------------------------------------------------
def test_noop_bot_verifier() -> None:
    noop = NoopBotVerifier()
    assert noop.verify(None, "1.2.3.4") is True
    assert noop.verify("", "1.2.3.4") is True
    assert noop.verify("any-token", "1.2.3.4", expected_action="contact") is True


# ---------------------------------------------------------------------------
# 12. Build Bot Verifier Factory Selection
# ---------------------------------------------------------------------------
def test_build_bot_verifier_factory() -> None:
    from pydantic import SecretStr

    class DummySettings:
        captcha_enabled = False
        turnstile_secret_key = SecretStr("dummy-secret")
        turnstile_allowed_hostnames = ["coralswift.com"]

    cfg = DummySettings()
    assert isinstance(build_bot_verifier(cfg), NoopBotVerifier)  # type: ignore[arg-type]

    cfg.captcha_enabled = True
    assert isinstance(build_bot_verifier(cfg), TurnstileVerifier)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 13. End-to-End Route Guard Verification Across All Protected Endpoints
# ---------------------------------------------------------------------------
PROTECTED_ENDPOINTS = [
    (
        "/api/v1/enquiries/contact",
        {
            "full_name": "Test",
            "business_email": "t@example.com",
            "phone": "+919820012345",
            "country": "IN",
            "privacy_consent": True,
            "enquiry_type": "general_information",
            "message": "Hello",
        },
    ),
    (
        "/api/v1/enquiries/project",
        {
            "full_name": "Test",
            "business_email": "t@example.com",
            "phone": "+919820012345",
            "country": "IN",
            "company_name": "Acme",
            "privacy_consent": True,
            "project_category": "custom_software",
            "requirement_summary": "Test project",
        },
    ),
    (
        "/api/v1/enquiries/partner",
        {
            "full_name": "Test",
            "designation": "Director",
            "business_email": "t@example.com",
            "phone": "+919820012345",
            "country": "IN",
            "company_name": "Acme",
            "privacy_consent": True,
        },
    ),
    (
        "/api/v1/enquiries/strategic",
        {
            "full_name": "Test",
            "designation": "Director",
            "business_email": "t@example.com",
            "phone": "+919820012345",
            "country": "IN",
            "company_name": "Acme",
            "privacy_consent": True,
        },
    ),
    (
        "/api/v1/meetings",
        {
            "full_name": "Test",
            "business_email": "t@example.com",
            "phone": "+919820012345",
            "country": "IN",
            "privacy_consent": True,
            "discussion_topic": "Services overview",
            "proposed_slots": [{"start": "2026-12-01T10:00:00Z", "end": "2026-12-01T10:30:00Z"}],
        },
    ),
    (
        "/api/v1/privacy/requests",
        {
            "email": "t@example.com",
            "request_type": "access",
            "full_name": "Test",
            "details": "Request details",
        },
    ),
    ("/api/v1/newsletter/subscribe", {"email": "t@example.com"}),
    ("/api/v1/newsletter/unsubscribe", {"email": "t@example.com", "token": "dummy-token"}),
]


def test_all_protected_endpoints_reject_missing_and_invalid_tokens() -> None:
    def cloudflare_handler(request: httpx.Request) -> httpx.Response:
        content = request.content.decode()
        if "response=valid-token" in content:
            return httpx.Response(200, json={"success": True, "hostname": "coralswift.com"})
        return httpx.Response(
            200, json={"success": False, "error-codes": ["invalid-input-response"]}
        )

    verifier = _make_verifier(cloudflare_handler, allowed_hostnames=["coralswift.com"])

    test_settings = Settings(
        _env_file=None,
        app_env="testing",
        database_url="postgresql+psycopg://user:pass@localhost:5432/dummy_test",
        secret_key="x" * 50,
        allowed_hosts=["testserver"],
        cors_allowed_origins=["http://localhost:3000"],
        captcha_enabled=True,
        turnstile_secret_key="dummy-test-secret-key",
        rate_limit_per_minute=0,
    )

    app = create_app(
        test_settings,
        storage=InMemoryStorage(),
        email_sender=RecordingEmail(),
        bot_verifier=verifier,
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        for path, payload in PROTECTED_ENDPOINTS:
            # 1. Missing X-Bot-Token header -> 403 BOT_CHECK_FAILED
            res_missing = client.post(path, json=payload)
            assert res_missing.status_code == 403, f"{path} did not reject missing token"
            assert res_missing.json()["error"]["code"] == "BOT_CHECK_FAILED"

            # 2. Blank X-Bot-Token header -> 403 BOT_CHECK_FAILED
            res_blank = client.post(path, json=payload, headers={"X-Bot-Token": "   "})
            assert res_blank.status_code == 403, f"{path} did not reject blank token"
            assert res_blank.json()["error"]["code"] == "BOT_CHECK_FAILED"

            # 3. Invalid X-Bot-Token header -> 403 BOT_CHECK_FAILED
            res_invalid = client.post(path, json=payload, headers={"X-Bot-Token": "invalid-token"})
            assert res_invalid.status_code == 403, f"{path} did not reject invalid token"
            assert res_invalid.json()["error"]["code"] == "BOT_CHECK_FAILED"

        # 4. Upload endpoint multipart check
        res_upload_missing = client.post(
            "/api/v1/documents/upload",
            data={"purpose": "project_attachment"},
            files={"file": ("test.pdf", b"%PDF-1.4...", "application/pdf")},
        )
        assert res_upload_missing.status_code == 403
        assert res_upload_missing.json()["error"]["code"] == "BOT_CHECK_FAILED"

        res_upload_invalid = client.post(
            "/api/v1/documents/upload",
            data={"purpose": "project_attachment"},
            files={"file": ("test.pdf", b"%PDF-1.4...", "application/pdf")},
            headers={"X-Bot-Token": "invalid-token"},
        )
        assert res_upload_invalid.status_code == 403
        assert res_upload_invalid.json()["error"]["code"] == "BOT_CHECK_FAILED"


# ---------------------------------------------------------------------------
# 14. Unprotected / Safe Public Endpoints Do NOT Require X-Bot-Token
# ---------------------------------------------------------------------------
def test_safe_public_endpoints_do_not_require_bot_token() -> None:
    # Even with CAPTCHA_ENABLED=True and a strict verifier, safe read endpoints
    # must not require X-Bot-Token.
    def strict_handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"success": False, "error-codes": ["invalid-input-response"]}
        )

    verifier = _make_verifier(strict_handler)

    test_settings = Settings(
        _env_file=None,
        app_env="testing",
        database_url="postgresql+psycopg://user:pass@localhost:5432/dummy_test",
        secret_key="x" * 50,
        allowed_hosts=["testserver"],
        cors_allowed_origins=["http://localhost:3000"],
        captcha_enabled=True,
        turnstile_secret_key="dummy-test-secret-key",
        rate_limit_per_minute=0,
    )

    app = create_app(
        test_settings,
        storage=InMemoryStorage(),
        email_sender=RecordingEmail(),
        bot_verifier=verifier,
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/health").status_code == 200
        assert client.get("/api/v1/meta").status_code == 200
