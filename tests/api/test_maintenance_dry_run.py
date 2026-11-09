"""`--dry-run` counts affected rows and changes nothing (test database only)."""

import importlib.util
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, update
from sqlalchemy.orm import Session

from app.common.utilities import utcnow
from app.core.config import Settings
from app.modules.admin import maintenance
from app.modules.enquiries.models import Enquiry
from app.modules.notifications.models import Notification
from app.modules.partner_documents.models import PartnerDocumentVersion
from tests import factories
from tests.fakes import InMemoryStorage, RecordingEmail

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "run_maintenance.py"


def _counts(db: Session) -> tuple[int, int, int]:
    return (
        db.scalar(
            select(func.count()).select_from(Enquiry).where(Enquiry.escalated_at.is_not(None))
        )
        or 0,
        db.scalar(select(func.count()).select_from(Notification)) or 0,
        db.scalar(select(func.count()).select_from(Enquiry)) or 0,
    )


def test_preview_counts_without_changing_anything(
    client: TestClient, db: Session, settings: Settings
) -> None:
    for _ in range(2):
        client.post("/api/v1/enquiries/contact", json=factories.contact())
    db.execute(update(Enquiry).values(response_due_at=utcnow() - timedelta(hours=1)))
    db.commit()
    before = _counts(db)

    result = maintenance.preview(client.app.state.sessionmaker, settings)  # type: ignore[attr-defined]

    assert result["sla_would_escalate"] == 2
    assert set(result) == {
        "idempotency_would_purge",
        "sla_would_escalate",
        "expiry_reminders_would_queue",
        "documents_would_purge",
        "notifications_would_dispatch",
    }
    assert _counts(db) == before  # nothing escalated, queued or created
    # the real job still acts afterwards: the dry run did not consume anything
    assert maintenance.escalate_overdue(db, settings) == 2


def test_script_dry_run_never_calls_real_jobs(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    engine: Engine,
    settings: Settings,
) -> None:
    spec = importlib.util.spec_from_file_location("run_maintenance", SCRIPT)
    assert spec and spec.loader
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)

    def boom(*_: Any, **__: Any) -> None:
        raise AssertionError("real job executed during --dry-run")

    monkeypatch.setattr(script, "load_settings", lambda: settings)  # test DB, never .env
    monkeypatch.setattr(script, "build_engine", lambda _s: engine)
    monkeypatch.setattr(script, "run_all", boom)
    monkeypatch.setattr(script, "build_storage", boom)
    monkeypatch.setattr(script, "build_email_sender", boom)

    assert script.main(["--dry-run"]) == 0
    assert "'dry_run': True" in capsys.readouterr().out


def test_preview_counts_expiry_and_retention_without_touching_them(
    client: TestClient,
    db: Session,
    settings: Settings,
    email: RecordingEmail,
    storage: InMemoryStorage,
) -> None:
    from tests.api.test_ops import ADM, sa_headers
    from tests.helpers import onboard_partner

    sa = sa_headers(client, db, settings)
    p = onboard_partner(client, db, settings, email)
    soon = (utcnow() + timedelta(days=10)).date().isoformat()
    doc_id = client.post(
        "/api/v1/partner/documents",
        headers=p.headers,
        data={"category": "registration_proof", "expires_on": soon},
        files={"file": ("r.pdf", factories.PDF, "application/pdf")},
    ).json()["data"]["id"]
    client.put(f"{ADM}/settings/expiry_reminder_days", headers=sa, json={"value": "30"})
    client.put(f"{ADM}/settings/retention.partner_document_days", headers=sa, json={"value": "1"})
    notifications = db.scalar(select(func.count()).select_from(Notification))

    first = maintenance.preview(client.app.state.sessionmaker, settings)  # type: ignore[attr-defined]
    assert first["expiry_reminders_would_queue"] == 1 and first["documents_would_purge"] == 0
    assert db.scalar(select(func.count()).select_from(Notification)) == notifications

    client.delete(f"/api/v1/partner/documents/{doc_id}", headers=p.headers)
    version = db.execute(select(PartnerDocumentVersion)).scalar_one()
    db.execute(
        update(PartnerDocumentVersion).values(retention_date=utcnow() - timedelta(seconds=1))
    )
    db.commit()

    second = maintenance.preview(client.app.state.sessionmaker, settings)  # type: ignore[attr-defined]
    assert second["documents_would_purge"] == 1
    assert storage.exists(version.storage_key)  # nothing deleted from storage
    db.refresh(version)
    assert version.purged_at is None  # nothing marked purged
    assert maintenance.purge_retained(db, storage) == 1  # the real job still has its work to do
