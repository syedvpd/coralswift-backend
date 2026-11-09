import threading
import uuid
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import Engine, delete, func, select, update
from sqlalchemy.orm import Session

from app.common import idempotency
from app.common.utilities import utcnow
from app.core.exceptions import AppError
from app.modules.enquiries.models import Enquiry
from tests import factories

URL = "/api/v1/enquiries/contact"


def key() -> dict[str, str]:
    return {"Idempotency-Key": f"test-{uuid.uuid4().hex}"}


def count(db: Session) -> int:
    return db.execute(select(func.count()).select_from(Enquiry)).scalar_one()


def test_same_key_same_payload_returns_original(client: TestClient, db: Session) -> None:
    h = key()
    first = client.post(URL, json=factories.contact(), headers=h)
    second = client.post(URL, json=factories.contact(), headers=h)
    assert first.status_code == second.status_code == 201
    assert second.json() == first.json() and second.headers["idempotent-replay"] == "true"
    assert count(db) == 1


def test_same_key_different_payload_rejected(client: TestClient, db: Session) -> None:
    h = key()
    client.post(URL, json=factories.contact(), headers=h)
    r = client.post(URL, json=factories.contact(message="A different message here"), headers=h)
    assert r.status_code == 422 and r.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert count(db) == 1


def test_key_is_scoped_per_endpoint(client: TestClient, db: Session) -> None:
    h = key()
    assert client.post(URL, json=factories.contact(), headers=h).status_code == 201
    assert (
        client.post("/api/v1/enquiries/project", json=factories.project(), headers=h).status_code
        == 201
    )
    assert count(db) == 2


def test_invalid_key_format(client: TestClient) -> None:
    r = client.post(URL, json=factories.contact(), headers={"Idempotency-Key": "short"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_IDEMPOTENCY_KEY"


def test_expired_key_is_reusable(client: TestClient, db: Session) -> None:
    h = key()
    first = client.post(URL, json=factories.contact(), headers=h).json()["data"]["reference_number"]
    db.execute(
        update(idempotency.IdempotencyKey).values(expires_at=utcnow() - timedelta(seconds=1))
    )
    db.commit()
    second = client.post(URL, json=factories.contact(), headers=h)
    assert second.status_code == 201 and "idempotent-replay" not in second.headers
    assert second.json()["data"]["reference_number"] != first
    assert idempotency.purge_expired(db) == 0  # the stale row was already replaced


def test_without_key_duplicates_are_not_merged(client: TestClient, db: Session) -> None:
    for _ in range(2):
        client.post(URL, json=factories.contact())
    assert count(db) == 2


def test_failed_attempt_releases_key(
    client: TestClient, db: Session, monkeypatch: MonkeyPatch
) -> None:
    h = key()
    real = "app.modules.enquiries.service.queue_submission_notifications"
    with monkeypatch.context() as m:
        m.setattr(real, lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
        assert client.post(URL, json=factories.contact(), headers=h).status_code == 500
    assert client.post(URL, json=factories.contact(), headers=h).status_code == 201
    assert count(db) == 1


def test_in_flight_duplicate_gets_409(client: TestClient, db: Session) -> None:
    h = key()
    payload = factories.contact()
    ctx = idempotency.claim(
        db,
        scope=f"POST {URL}",
        client_ip="testclient",
        key=h["Idempotency-Key"],
        payload=_normalized(payload),
        ttl_hours=1,
    )
    assert isinstance(ctx, idempotency.IdemContext)
    r = client.post(URL, json=payload, headers=h)
    assert r.status_code in (409, 422)  # 409 in progress; 422 if normalisation changed the hash
    assert count(db) == 0


def _normalized(payload: dict[str, Any]) -> dict[str, Any]:
    from app.modules.enquiries.schemas import ContactEnquiryIn

    return ContactEnquiryIn(**payload).model_dump(mode="json")


def test_concurrent_claims_have_one_winner(engine: Engine) -> None:
    """Real, separately committed connections: the unique constraint picks exactly one winner."""
    k = f"conc-{uuid.uuid4().hex}"
    outcomes: list[str] = []
    barrier = threading.Barrier(4)

    def worker() -> None:
        with Session(engine) as s:
            barrier.wait()
            try:
                res = idempotency.claim(
                    s, scope="POST /test", client_ip="1.2.3.4", key=k, payload={"a": 1}, ttl_hours=1
                )
                outcomes.append("won" if isinstance(res, idempotency.IdemContext) else "replay")
            except AppError as exc:
                outcomes.append(exc.code)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    with Session(engine) as s:  # remove only this test's own row from the disposable test DB
        s.execute(delete(idempotency.IdempotencyKey).where(idempotency.IdempotencyKey.key == k))
        s.commit()
    assert outcomes.count("won") == 1 and outcomes.count("REQUEST_IN_PROGRESS") == 3


@pytest.mark.parametrize("n", [8])
def test_reference_numbers_unique_under_concurrency(engine: Engine, n: int) -> None:
    from app.modules.enquiries.service import next_reference

    refs: list[str] = []

    def worker() -> None:
        with Session(engine) as s:
            refs.append(next_reference(s))

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(refs) == n and len(set(refs)) == n
