"""Scan-status foundation. No malware scanner is configured (owner accepted quarantine-only
2026-11-10), so every stored file honestly reports `not_scanned`; nothing is ever marked clean."""

from typing import Literal

from pydantic import BaseModel, computed_field

from app.modules.documents.constants import scan_status_of

ScanStatus = Literal["not_scanned", "scan_pending", "clean", "infected", "scan_failed"]


class ScanStatusMixin(BaseModel):
    @computed_field  # type: ignore[prop-decorator]
    @property
    def scan_status(self) -> ScanStatus:
        return scan_status_of(str(getattr(self, "upload_status", "quarantined")))  # type: ignore[return-value]
