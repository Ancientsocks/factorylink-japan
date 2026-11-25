"""Private document storage for FactoryLink.

Local filesystem storage is intended for development and single-instance tests.
Production deployments must use a private S3 bucket so documents survive service
replacement and are shared across API instances. S3 SDK imports are lazy so local
unit tests do not require AWS credentials or a live S3 endpoint.
"""
from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from .config import settings

_STORAGE_KEY = re.compile(r"^[a-f0-9]{32}\.(?:pdf|png|jpg|jpeg|csv|xlsx)$")


class StorageError(RuntimeError):
    """Raised when the configured document storage backend is unavailable."""


class StorageObjectNotFound(StorageError):
    """Raised when a document object does not exist in configured storage."""


def validate_storage_configuration(config: Any = settings) -> None:
    """Fail closed on unsafe or incomplete production document-storage settings."""
    provider = str(config.storage_provider).strip().lower()
    if provider not in {"local", "s3"}:
        raise RuntimeError("STORAGE_PROVIDER must be either 'local' or 's3'.")
    if str(config.environment).strip().lower() != "production":
        return
    if provider != "s3":
        raise RuntimeError(
            "Production requires STORAGE_PROVIDER=s3; local container files are not durable shared storage."
        )
    if not str(config.storage_s3_bucket).strip():
        raise RuntimeError("Production S3 storage requires STORAGE_S3_BUCKET.")
    if not str(config.storage_s3_region).strip():
        raise RuntimeError("Production S3 storage requires STORAGE_S3_REGION.")
    access_key = str(config.storage_s3_access_key_id).strip()
    secret_key = str(config.storage_s3_secret_access_key).strip()
    if bool(access_key) != bool(secret_key):
        raise RuntimeError("STORAGE_S3_ACCESS_KEY_ID and STORAGE_S3_SECRET_ACCESS_KEY must be configured together.")
    endpoint = str(config.storage_s3_endpoint_url).strip()
    if endpoint and not endpoint.startswith("https://"):
        raise RuntimeError("Production STORAGE_S3_ENDPOINT_URL must use HTTPS.")


def _validated_key(storage_name: str) -> str:
    if not isinstance(storage_name, str) or not _STORAGE_KEY.fullmatch(storage_name):
        raise ValueError("Invalid document storage key.")
    return storage_name


def _local_path(storage_name: str) -> Path:
    key = _validated_key(storage_name)
    root = Path(settings.upload_dir).expanduser().resolve()
    path = (root / key).resolve()
    if path.parent != root:
        raise ValueError("Document storage path escaped its configured directory.")
    return path


def _get_s3_client():
    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:  # pragma: no cover - exercised in production packaging
        raise StorageError("S3 storage requires the boto3 dependency. Rebuild the backend image.") from exc

    options: dict[str, Any] = {
        "region_name": settings.storage_s3_region,
        "config": Config(
            signature_version="s3v4",
            retries={"max_attempts": 4, "mode": "standard"},
            connect_timeout=5,
            read_timeout=30,
        ),
    }
    if settings.storage_s3_endpoint_url.strip():
        options["endpoint_url"] = settings.storage_s3_endpoint_url.strip()
    if settings.storage_s3_access_key_id.strip():
        options["aws_access_key_id"] = settings.storage_s3_access_key_id.strip()
        options["aws_secret_access_key"] = settings.storage_s3_secret_access_key
    # When explicit credentials are absent, boto3 uses its standard provider
    # chain (for example, an ECS task role or EC2 instance profile).
    return boto3.client("s3", **options)


def save_document(storage_name: str, content: bytes, content_type: str) -> None:
    key = _validated_key(storage_name)
    if not content:
        raise ValueError("Cannot store an empty document.")
    if settings.storage_provider.strip().lower() == "local":
        path = _local_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(prefix=f".{key}.", suffix=".tmp", dir=path.parent, delete=False) as stream:
                temp_path = Path(stream.name)
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_path, path)
        except OSError as exc:
            if temp_path:
                temp_path.unlink(missing_ok=True)
            raise StorageError("Could not persist the uploaded document locally.") from exc
        return

    if settings.storage_provider.strip().lower() != "s3":
        raise StorageError("Unsupported document storage provider.")
    bucket = settings.storage_s3_bucket.strip()
    if not bucket:
        raise StorageError("S3 document bucket is not configured.")
    try:
        _get_s3_client().put_object(
            Bucket=bucket,
            Key=key,
            Body=content,
            ContentType=content_type,
            Metadata={"sha256": hashlib.sha256(content).hexdigest()},
        )
    except Exception as exc:
        raise StorageError("The document storage service could not save the uploaded file.") from exc


def read_document(storage_name: str) -> bytes:
    key = _validated_key(storage_name)
    if settings.storage_provider.strip().lower() == "local":
        path = _local_path(key)
        try:
            return path.read_bytes()
        except FileNotFoundError as exc:
            raise StorageObjectNotFound("Stored document was not found.") from exc
        except OSError as exc:
            raise StorageError("The local document storage could not read this file.") from exc

    if settings.storage_provider.strip().lower() != "s3":
        raise StorageError("Unsupported document storage provider.")
    bucket = settings.storage_s3_bucket.strip()
    if not bucket:
        raise StorageError("S3 document bucket is not configured.")
    try:
        response = _get_s3_client().get_object(Bucket=bucket, Key=key)
        body = response["Body"]
        try:
            return body.read()
        finally:
            close = getattr(body, "close", None)
            if callable(close):
                close()
    except Exception as exc:
        code = None
        response = getattr(exc, "response", None)
        if isinstance(response, dict):
            code = response.get("Error", {}).get("Code")
        if code in {"NoSuchKey", "NotFound", "404"}:
            raise StorageObjectNotFound("Stored document was not found.") from exc
        raise StorageError("The document storage service could not read this file.") from exc


def delete_document(storage_name: str) -> None:
    key = _validated_key(storage_name)
    if settings.storage_provider.strip().lower() == "local":
        try:
            _local_path(key).unlink(missing_ok=True)
        except OSError as exc:
            raise StorageError("The local document storage could not remove this file.") from exc
        return

    if settings.storage_provider.strip().lower() != "s3":
        raise StorageError("Unsupported document storage provider.")
    bucket = settings.storage_s3_bucket.strip()
    if not bucket:
        raise StorageError("S3 document bucket is not configured.")
    try:
        _get_s3_client().delete_object(Bucket=bucket, Key=key)
    except Exception as exc:
        raise StorageError("The document storage service could not remove this file.") from exc
