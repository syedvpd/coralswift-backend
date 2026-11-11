"""Malware scanner adapter (ClamAV `clamd` INSTREAM protocol). Disabled by default.

With SCANNER_BACKEND=none nothing is scanned and files stay quarantined (`not_scanned`). With
SCANNER_BACKEND=clamav every upload is scanned before it can be reviewed or downloaded, and the
system fails closed: if clamd is unreachable the file stays quarantined as `scan_failed`."""

import logging
import socket
import struct
from dataclasses import dataclass
from typing import Literal, Protocol

logger = logging.getLogger("app.scanner")
CHUNK = 64 * 1024


@dataclass(frozen=True)
class ScanResult:
    verdict: Literal["clean", "infected", "error"]
    detail: str = ""


class Scanner(Protocol):
    def scan(self, data: bytes) -> ScanResult: ...


class ClamAVScanner:
    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.host, self.port, self.timeout = host, port, timeout

    def scan(self, data: bytes) -> ScanResult:
        try:
            with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
                sock.settimeout(self.timeout)
                sock.sendall(b"zINSTREAM\0")
                for i in range(0, len(data), CHUNK):
                    chunk = data[i : i + CHUNK]
                    sock.sendall(struct.pack(">I", len(chunk)) + chunk)
                sock.sendall(struct.pack(">I", 0))
                reply = b""
                while not reply.endswith(b"\0") and len(reply) < 4096:
                    part = sock.recv(1024)
                    if not part:
                        break
                    reply += part
        except OSError:
            logger.error("scanner unreachable")  # no file content or names are logged
            return ScanResult("error", "scanner unreachable")
        text = reply.rstrip(b"\0\n ").decode("ascii", "replace")
        if text.endswith("OK"):
            return ScanResult("clean")
        if text.endswith("FOUND"):
            return ScanResult("infected", text.split(":", 1)[-1].replace("FOUND", "").strip())
        return ScanResult("error", "unexpected scanner reply")


# Process-wide, set once by create_app (tests replace it).
_active: Scanner | None = None


def set_scanner(scanner: Scanner | None) -> None:
    global _active
    _active = scanner


def active_scanner() -> Scanner | None:
    return _active
