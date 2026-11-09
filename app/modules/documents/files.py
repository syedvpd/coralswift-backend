"""Upload content validation: extension allow-list + magic-byte sniffing (never trust headers)."""

import hashlib
import io
import re
import zipfile
from dataclasses import dataclass

from app.core.exceptions import AppError

_MAX_UNZIPPED = 100 * 1024 * 1024
_MAX_ZIP_ENTRIES = 2000


@dataclass(frozen=True)
class FileKind:
    extension: str  # canonical, used for the storage key
    content_type: str
    aliases: frozenset[str]  # declared types we tolerate for this kind


KINDS = {
    "pdf": FileKind("pdf", "application/pdf", frozenset({"application/pdf"})),
    "png": FileKind("png", "image/png", frozenset({"image/png"})),
    "jpg": FileKind("jpg", "image/jpeg", frozenset({"image/jpeg", "image/jpg"})),
    "docx": FileKind(
        "docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        frozenset({"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}),
    ),
    "xlsx": FileKind(
        "xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        frozenset({"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}),
    ),
}
EXTENSION_TO_KIND = {
    "pdf": "pdf",
    "png": "png",
    "jpg": "jpg",
    "jpeg": "jpg",
    "docx": "docx",
    "xlsx": "xlsx",
}
_GENERIC = {"", "application/octet-stream"}


def unsupported(message: str) -> AppError:
    return AppError(message, status_code=415, code="UNSUPPORTED_FILE_TYPE")


def sanitize_filename(raw: str | None) -> str:
    """Display name only: basename, no control chars. Never used to build a storage path."""
    name = (raw or "").replace("\\", "/").split("/")[-1]
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip().strip(".")
    name = re.sub(r"\s+", " ", name)
    return name[:150] or "file"


def _zip_kind(data: bytes) -> str | None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            infos = zf.infolist()
            if len(infos) > _MAX_ZIP_ENTRIES or sum(i.file_size for i in infos) > _MAX_UNZIPPED:
                return None
            names = {i.filename for i in infos}
    except zipfile.BadZipFile:
        return None
    if "word/document.xml" in names:
        return "docx"
    if "xl/workbook.xml" in names:
        return "xlsx"
    return None


def detect_kind(data: bytes) -> str | None:
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith(b"PK\x03\x04"):
        return _zip_kind(data)
    return None


@dataclass(frozen=True)
class ValidatedFile:
    kind: FileKind
    size: int
    sha256: str
    display_name: str


def validate_upload(
    *, data: bytes, filename: str | None, declared_type: str | None, max_bytes: int
) -> ValidatedFile:
    if len(data) > max_bytes:
        raise AppError("File is too large", status_code=413, code="FILE_TOO_LARGE")
    if not data:
        raise AppError("File is empty", status_code=422, code="EMPTY_FILE")
    display = sanitize_filename(filename)
    ext = display.rsplit(".", 1)[-1].lower() if "." in display else ""
    if ext not in EXTENSION_TO_KIND:
        raise unsupported("File type is not allowed")
    detected = detect_kind(data)
    if detected is None or detected != EXTENSION_TO_KIND[ext]:
        raise unsupported("File content does not match its extension")
    kind = KINDS[detected]
    declared = (declared_type or "").split(";")[0].strip().lower()
    if declared not in _GENERIC and declared not in kind.aliases:
        raise unsupported("Declared content type does not match file content")
    return ValidatedFile(kind, len(data), hashlib.sha256(data).hexdigest(), display)
