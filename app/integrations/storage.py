"""Private object storage. Keys are server-generated; nothing here ever yields a public URL."""

import os
import re
import tempfile
from pathlib import Path
from typing import Any, Protocol

from app.core.config import Settings

_SAFE_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/_.-]*$")


class StorageError(Exception):
    pass


class Storage(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def delete(self, key: str) -> None: ...
    def exists(self, key: str) -> bool: ...
    def get(self, key: str) -> bytes: ...


class LocalStorage:
    """Filesystem storage for development. Root must live outside any served directory."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        if not _SAFE_KEY.match(key) or ".." in key:
            raise StorageError("invalid storage key")
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise StorageError("invalid storage key")
        return path

    def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            # Write-then-rename so a crash never leaves a half-written object under the key.
            fd, tmp = tempfile.mkstemp(dir=path.parent)
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            os.replace(tmp, path)
        except OSError as exc:
            raise StorageError("local write failed") from exc

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def get(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except OSError as exc:
            raise StorageError("local read failed") from exc

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()


class S3Storage:
    """Keys under `partners/` go to the partner bucket when one is configured."""

    def __init__(self, client: Any, bucket: str, partner_bucket: str | None = None) -> None:
        self.client = client
        self.bucket = bucket
        self.partner_bucket = partner_bucket

    def _bucket(self, key: str) -> str:
        return (
            self.partner_bucket
            if self.partner_bucket and key.startswith("partners/")
            else self.bucket
        )

    def put(self, key: str, data: bytes, content_type: str) -> None:
        try:
            # No per-object SSE header: S3-compatible stores (Supabase) encrypt at rest themselves.
            self.client.put_object(
                Bucket=self._bucket(key), Key=key, Body=data, ContentType=content_type
            )
        except Exception as exc:  # boto raises many types; never leak details to clients
            raise StorageError("object store write failed") from exc

    def delete(self, key: str) -> None:
        try:
            self.client.delete_object(Bucket=self._bucket(key), Key=key)
        except Exception as exc:
            raise StorageError("object store delete failed") from exc

    def get(self, key: str) -> bytes:
        try:
            response = self.client.get_object(Bucket=self._bucket(key), Key=key)
            return bytes(response["Body"].read())
        except Exception as exc:
            raise StorageError("object store read failed") from exc

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self._bucket(key), Key=key)
        except Exception:
            return False
        return True


def build_storage(settings: Settings) -> Storage:
    if settings.storage_backend == "local":
        return LocalStorage(settings.storage_local_root)
    import boto3  # type: ignore[import-untyped]  # imported lazily; boto3 ships without type markers
    from botocore.config import Config  # type: ignore[import-untyped]

    client = boto3.client(
        "s3",
        region_name=settings.s3_region,
        endpoint_url=settings.s3_endpoint_url,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        aws_access_key_id=(
            settings.s3_access_key_id.get_secret_value() if settings.s3_access_key_id else None
        ),
        aws_secret_access_key=(
            settings.s3_secret_access_key.get_secret_value()
            if settings.s3_secret_access_key
            else None
        ),
    )
    if not settings.s3_bucket:
        raise ValueError("S3_BUCKET is required when STORAGE_BACKEND=s3")
    return S3Storage(client, settings.s3_bucket, settings.s3_partner_bucket)
