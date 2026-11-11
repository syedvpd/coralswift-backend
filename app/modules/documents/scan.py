"""Scan-status foundation. No malware scanner is configured (owner accepted quarantine-only
2026-11-10), so every stored file honestly reports `not_scanned`; nothing is ever marked clean."""

from typing import Literal

from pydantic import BaseModel, computed_field

ScanStatus = Literal["not_scanned", "clean", "infected", "scan_failed"]


class ScanStatusMixin(BaseModel):
    @computed_field  # type: ignore[prop-decorator]
    @property
    def scan_status(self) -> ScanStatus:
        # shortcut: constant until a scanner exists; derive from a stored result then.
        return "not_scanned"
