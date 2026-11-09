from typing import Annotated

import pytest
from fastapi import FastAPI, Query
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.exceptions import ConflictError
from app.main import create_app
from tests.conftest import TEST_ORIGIN
from tests.fakes import InMemoryStorage, RecordingEmail


@pytest.fixture
def probe_app(app: FastAPI) -> FastAPI:
    """App plus throwaway routes that exercise the error paths."""

    @app.get("/_probe/validate")
    def validate(n: Annotated[int, Query()]) -> dict[str, int]:
        return {"n": n}

    @app.get("/_probe/boom")
    def boom() -> None:
        raise RuntimeError("secret internal detail password=hunter2")

    @app.get("/_probe/conflict")
    def conflict() -> None:
        raise ConflictError("Already exists", details=[{"field": "email"}])

    return app


@pytest.fixture
def probe(probe_app: FastAPI) -> TestClient:
    return TestClient(probe_app, raise_server_exceptions=False)


def test_startup_and_openapi(client: TestClient) -> None:
    assert client.get("/docs").status_code == 200
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/meta" in paths and "/health/ready" in paths


def test_api_v1_meta(client: TestClient, settings: Settings) -> None:
    body = client.get("/api/v1/meta").json()
    assert body["success"] is True
    assert body["data"] == {"name": settings.app_name, "version": settings.app_version, "api": "v1"}


def test_request_id_generated_and_echoed(client: TestClient) -> None:
    assert len(client.get("/health").headers["x-request-id"]) == 32
    echoed = client.get("/health", headers={"X-Request-ID": "trace-12345678"})
    assert echoed.headers["x-request-id"] == "trace-12345678"
    bad = client.get("/health", headers={"X-Request-ID": "bad id\twith junk"})
    assert bad.headers["x-request-id"] != "bad id\twith junk"


def test_security_headers(client: TestClient) -> None:
    assert client.get("/health").headers["x-content-type-options"] == "nosniff"


def test_not_found_envelope(client: TestClient) -> None:
    r = client.get("/nope")
    assert r.status_code == 404
    assert r.json() == {
        "success": False,
        "message": "Not Found",
        "error": {"code": "NOT_FOUND", "details": []},
    }


def test_validation_error_envelope(probe: TestClient) -> None:
    r = probe.get("/_probe/validate?n=abc")
    body = r.json()
    assert r.status_code == 422 and body["success"] is False
    assert body["error"]["code"] == "VALIDATION_ERROR"
    detail = body["error"]["details"][0]
    assert detail["source"] == "query" and detail["field"] == "n"
    assert "input" not in detail


def test_app_error_envelope(probe: TestClient) -> None:
    r = probe.get("/_probe/conflict")
    assert r.status_code == 409
    assert r.json()["error"] == {"code": "CONFLICT", "details": [{"field": "email"}]}


def test_unexpected_exception_hides_internals(probe: TestClient) -> None:
    r = probe.get("/_probe/boom")
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "hunter2" not in r.text and "RuntimeError" not in r.text
    assert "x-request-id" in r.headers


def test_cors_allowed_and_blocked_origin(client: TestClient) -> None:
    ok = client.get("/health", headers={"Origin": TEST_ORIGIN})
    assert ok.headers["access-control-allow-origin"] == TEST_ORIGIN
    bad = client.get("/health", headers={"Origin": "http://evil.test"})
    assert "access-control-allow-origin" not in bad.headers
    pre = client.options(
        "/health",
        headers={"Origin": TEST_ORIGIN, "Access-Control-Request-Method": "GET"},
    )
    assert pre.status_code == 200


def test_cors_allows_phase_1_custom_headers(client: TestClient) -> None:
    pre = client.options(
        "/api/v1/enquiries/contact",
        headers={
            "Origin": TEST_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": ("idempotency-key, x-bot-token, x-lookup-token"),
        },
    )
    assert pre.status_code == 200
    allowed = pre.headers["access-control-allow-headers"].lower()
    assert "idempotency-key" in allowed
    assert "x-bot-token" in allowed
    assert "x-lookup-token" in allowed


def test_untrusted_host_rejected(client: TestClient) -> None:
    assert client.get("/health", headers={"Host": "evil.example"}).status_code == 400


def test_docs_disabled_in_production(settings: Settings) -> None:
    prod = Settings(
        _env_file=None,
        app_env="production",
        database_url=settings.database_url,
        secret_key="p" * 48,
        allowed_hosts=["testserver"],
        storage_backend="s3",
        s3_bucket="bucket",
        email_backend="brevo",
        brevo_api_key="key",
        email_sender_address="noreply@example.com",
        captcha_enabled=True,
        turnstile_secret_key="secret",
    )
    with TestClient(
        create_app(prod, storage=InMemoryStorage(), email_sender=RecordingEmail())
    ) as c:
        assert c.get("/docs").status_code == 404
        assert "strict-transport-security" in c.get("/health").headers
