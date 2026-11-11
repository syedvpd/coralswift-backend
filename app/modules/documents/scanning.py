"""Apply the configured scanner to a stored upload and map the verdict to an upload status."""

from app.integrations.scanner import active_scanner
from app.modules.documents.constants import UploadStatus


def scan_upload(data: bytes) -> UploadStatus:
    """No scanner: quarantined (not_scanned). Scanner: clean / rejected (infected). A scanner
    failure fails closed: the file stays `failed` (scan_failed) and cannot be reviewed or
    downloaded until it is rescanned."""
    scanner = active_scanner()
    if scanner is None:
        return UploadStatus.QUARANTINED
    result = scanner.scan(data)
    if result.verdict == "clean":
        return UploadStatus.CLEAN
    if result.verdict == "infected":
        return UploadStatus.REJECTED
    return UploadStatus.FAILED
