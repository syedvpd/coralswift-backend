from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import Settings
from app.main import create_app


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["data"] == {"status": "ok"}


def test_live(client: TestClient) -> None:
    r = client.get("/health/live")
    assert r.status_code == 200 and r.json()["data"] == {"status": "alive"}


def test_ready_with_database(client: TestClient) -> None:
    r = client.get("/health/ready")
    assert r.status_code == 200
    assert r.json()["data"] == {"status": "ready", "database": "ok"}


def test_ready_503_when_database_down_and_no_credentials_leak(settings: Settings) -> None:
    dead = settings.model_copy(
        update={
            "database_url": SecretStr("postgresql+psycopg://leaky:s3cr3tpw@127.0.0.1:1/nothing")
        }
    )
    with TestClient(create_app(dead)) as c:
        r = c.get("/health/ready")
        assert r.status_code == 503
        body = r.json()
        assert body["success"] is False and body["error"]["code"] == "NOT_READY"
        assert "s3cr3tpw" not in r.text and "leaky" not in r.text
        # liveness must stay up even when the DB is down
        assert c.get("/health/live").status_code == 200
