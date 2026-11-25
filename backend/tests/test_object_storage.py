from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

import pytest

from app import object_storage
from app.config import settings


KEY = "a" * 32 + ".pdf"


def test_local_document_storage_roundtrip_is_atomic_and_deletes(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_provider", "local")
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))

    payload = b"%PDF-1.7\nFactoryLink test"
    object_storage.save_document(KEY, payload, "application/pdf")

    target = tmp_path / "uploads" / KEY
    assert target.read_bytes() == payload
    assert object_storage.read_document(KEY) == payload
    assert list(target.parent.iterdir()) == [target]

    object_storage.delete_document(KEY)
    assert not target.exists()


def test_storage_rejects_path_traversal_and_uncontrolled_keys():
    for value in ("../secret.pdf", "/etc/passwd", "not-a-uuid.pdf", "a" * 32 + ".exe"):
        with pytest.raises(ValueError, match="Invalid document storage key"):
            object_storage._validated_key(value)


def test_s3_storage_roundtrip_uses_private_object_calls(monkeypatch):
    monkeypatch.setattr(settings, "storage_provider", "s3")
    monkeypatch.setattr(settings, "storage_s3_bucket", "factorylink-private-test")
    calls = []
    content = b"%PDF-1.7\nS3 storage test"

    class FakeBody:
        def __init__(self, payload):
            self.payload = BytesIO(payload)
            self.was_closed = False

        def read(self):
            return self.payload.read()

        def close(self):
            self.was_closed = True

    body = FakeBody(content)

    class FakeS3:
        def put_object(self, **kwargs):
            calls.append(("put", kwargs))

        def get_object(self, **kwargs):
            calls.append(("get", kwargs))
            return {"Body": body}

        def delete_object(self, **kwargs):
            calls.append(("delete", kwargs))

    monkeypatch.setattr(object_storage, "_get_s3_client", lambda: FakeS3())

    object_storage.save_document(KEY, content, "application/pdf")
    assert object_storage.read_document(KEY) == content
    assert body.was_closed is True
    object_storage.delete_document(KEY)

    assert [call[0] for call in calls] == ["put", "get", "delete"]
    assert calls[0][1]["Bucket"] == "factorylink-private-test"
    assert calls[0][1]["Key"] == KEY
    assert calls[0][1]["ContentType"] == "application/pdf"
    assert calls[0][1]["Metadata"]["sha256"]
    assert calls[2][1] == {"Bucket": "factorylink-private-test", "Key": KEY}


def test_production_storage_requires_private_s3_and_credential_pair():
    base = dict(
        environment="production",
        storage_provider="s3",
        storage_s3_bucket="factorylink-prod-documents",
        storage_s3_region="ap-northeast-1",
        storage_s3_endpoint_url="",
        storage_s3_access_key_id="access",
        storage_s3_secret_access_key="secret",
    )
    config = SimpleNamespace(**base)
    object_storage.validate_storage_configuration(config)

    config.storage_provider = "local"
    with pytest.raises(RuntimeError, match="requires STORAGE_PROVIDER=s3"):
        object_storage.validate_storage_configuration(config)

    config.storage_provider = "s3"
    config.storage_s3_secret_access_key = ""
    with pytest.raises(RuntimeError, match="must be configured together"):
        object_storage.validate_storage_configuration(config)

    config.storage_s3_secret_access_key = "secret"
    config.storage_s3_endpoint_url = "http://minio.internal:9000"
    with pytest.raises(RuntimeError, match="must use HTTPS"):
        object_storage.validate_storage_configuration(config)


def test_s3_client_uses_default_credential_chain_when_keys_are_empty(monkeypatch):
    captured = {}

    class FakeConfig:
        def __init__(self, **kwargs):
            captured["config"] = kwargs

    class FakeBoto3:
        def client(self, service_name, **kwargs):
            captured["service_name"] = service_name
            captured["client_kwargs"] = kwargs
            return object()

    monkeypatch.setattr(settings, "storage_s3_region", "ap-northeast-1")
    monkeypatch.setattr(settings, "storage_s3_endpoint_url", "")
    monkeypatch.setattr(settings, "storage_s3_access_key_id", "")
    monkeypatch.setattr(settings, "storage_s3_secret_access_key", "")
    import sys
    import types

    fake_botocore = types.ModuleType("botocore")
    fake_config_module = types.ModuleType("botocore.config")
    fake_config_module.Config = FakeConfig
    fake_botocore.config = fake_config_module
    monkeypatch.setitem(sys.modules, "boto3", FakeBoto3())
    monkeypatch.setitem(sys.modules, "botocore", fake_botocore)
    monkeypatch.setitem(sys.modules, "botocore.config", fake_config_module)

    object_storage._get_s3_client()

    assert captured["service_name"] == "s3"
    assert captured["client_kwargs"]["region_name"] == "ap-northeast-1"
    assert "aws_access_key_id" not in captured["client_kwargs"]
    assert "aws_secret_access_key" not in captured["client_kwargs"]
    assert captured["config"]["signature_version"] == "s3v4"
    assert captured["config"]["retries"]["max_attempts"] == 4


def test_s3_missing_object_is_mapped_to_not_found(monkeypatch):
    class FakeClientError(Exception):
        response = {"Error": {"Code": "NoSuchKey"}}

    class FakeS3:
        def get_object(self, **kwargs):
            raise FakeClientError("missing")

    monkeypatch.setattr(settings, "storage_provider", "s3")
    monkeypatch.setattr(settings, "storage_s3_bucket", "factorylink-private-test")
    monkeypatch.setattr(object_storage, "_get_s3_client", lambda: FakeS3())

    with pytest.raises(object_storage.StorageObjectNotFound):
        object_storage.read_document(KEY)


def test_s3_service_failure_is_mapped_to_storage_error(monkeypatch):
    class FakeS3:
        def get_object(self, **kwargs):
            raise TimeoutError("upstream unavailable")

    monkeypatch.setattr(settings, "storage_provider", "s3")
    monkeypatch.setattr(settings, "storage_s3_bucket", "factorylink-private-test")
    monkeypatch.setattr(object_storage, "_get_s3_client", lambda: FakeS3())

    with pytest.raises(object_storage.StorageError, match="could not read"):
        object_storage.read_document(KEY)
