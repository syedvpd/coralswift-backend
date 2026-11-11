from collections.abc import Callable

import httpx

from app.integrations.botcheck import NoopBotVerifier, TurnstileVerifier
from tests.conftest import AppFactory


def _verifier(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    allowed_hostnames: list[str] | None = None,
) -> TurnstileVerifier:
    return TurnstileVerifier(
        "s",
        httpx.Client(transport=httpx.MockTransport(handler)),
        allowed_hostnames=allowed_hostnames,
    )


def test_turnstile_accepts_success_and_sends_secret() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.content.decode()
        return httpx.Response(200, json={"success": True})

    assert _verifier(handler).verify("tok", "1.2.3.4")
    assert "secret=s" in seen["body"] and "response=tok" in seen["body"]


def test_turnstile_fails_closed() -> None:
    def ok_false(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": False})

    def boom(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    def garbage(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    assert not _verifier(ok_false).verify("tok", "ip")
    assert not _verifier(boom).verify("tok", "ip")
    assert not _verifier(garbage).verify("tok", "ip")
    assert not _verifier(ok_false).verify(None, "ip")
    assert not _verifier(ok_false).verify("   ", "ip")
    assert not _verifier(ok_false).verify("x" * 2049, "ip")
    assert not _verifier(lambda _: httpx.Response(502)).verify("tok", "ip")


def test_turnstile_hostname_restriction() -> None:
    v = _verifier(
        lambda r: httpx.Response(200, json={"success": True, "hostname": "coralswift.com"}),
        allowed_hostnames=["coralswift.com", "coralswift-ochre.vercel.app"],
    )
    assert v.verify("tok", "ip")

    wrong = _verifier(
        lambda r: httpx.Response(200, json={"success": True, "hostname": "evil.example"}),
        allowed_hostnames=["coralswift.com"],
    )
    missing = _verifier(
        lambda r: httpx.Response(200, json={"success": True}),
        allowed_hostnames=["coralswift.com"],
    )
    assert not wrong.verify("tok", "ip")
    assert not missing.verify("tok", "ip")


def test_turnstile_whitespace_or_oversize_skips_provider_call() -> None:
    called = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal called
        called += 1
        return httpx.Response(200, json={"success": True})

    v = _verifier(handler)
    assert not v.verify(None, "ip")
    assert not v.verify("   \t ", "ip")
    assert not v.verify("a" * 2049, "ip")
    assert called == 0
    assert v.verify("  good-tok  ", "ip")
    assert called == 1


def test_noop_allows_everything() -> None:
    assert NoopBotVerifier().verify(None, "ip")


def test_build_bot_verifier_selection() -> None:
    from pydantic import SecretStr

    from app.integrations.botcheck import build_bot_verifier

    class S:
        captcha_enabled = False
        turnstile_secret_key = SecretStr("x")
        turnstile_allowed_hostnames = ["coralswift.com"]

    assert isinstance(build_bot_verifier(S()), NoopBotVerifier)  # type: ignore[arg-type]
    S.captcha_enabled = True
    assert isinstance(build_bot_verifier(S()), TurnstileVerifier)  # type: ignore[arg-type]


def test_api_rejects_missing_invalid_and_expired_tokens(app_factory: AppFactory) -> None:
    from fastapi.testclient import TestClient

    from tests import factories

    def cloudflare(request: httpx.Request) -> httpx.Response:
        good = "response=good" in request.content.decode()
        body = (
            {"success": good}
            if good
            else {"success": False, "error-codes": ["timeout-or-duplicate"]}
        )
        return httpx.Response(200, json=body)

    app = app_factory(bot_verifier=_verifier(cloudflare))
    url = "/api/v1/enquiries/contact"
    with TestClient(app, raise_server_exceptions=False) as c:
        for headers in ({}, {"X-Bot-Token": "invalid"}, {"X-Bot-Token": "expired"}):
            r = c.post(url, json=factories.contact(), headers=headers)
            assert r.status_code == 403 and r.json()["error"]["code"] == "BOT_CHECK_FAILED"
        ok = c.post(url, json=factories.contact(), headers={"X-Bot-Token": "good"})
        assert ok.status_code == 201
