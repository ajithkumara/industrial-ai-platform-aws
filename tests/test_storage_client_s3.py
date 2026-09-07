"""
Tests for consumer/storage_client.py (Amazon S3), using moto to emulate S3.

Proves the AWS raw/Bronze contract matches the Azure ADLS reference logically:
  - upload_batch writes ONE JSONL object under raw/telemetry/year=/month=/day=/
  - each line is one event, round-trippable
  - write_to_dlq writes a single JSON object under raw/telemetry/_dlq/...
  - empty batch raises (BatchBuffer never issues a no-op write + checkpoint)
  - keys are date-partitioned and deterministic in structure
"""

from __future__ import annotations

import json

import boto3
import pytest
from moto import mock_aws

from consumer.storage_client import StorageClient

_BUCKET = "test-industrial-ai-raw"
_REGION = "ca-central-1"


@pytest.fixture
def s3_bucket(monkeypatch):
    monkeypatch.setenv("S3_BUCKET", _BUCKET)
    monkeypatch.setenv("AWS_REGION", _REGION)
    monkeypatch.setenv("RAW_FOLDER", "raw/telemetry")
    import importlib
    import config.settings as settings_module
    importlib.reload(settings_module)
    # storage_client bound `settings` at its import; rebind to the reloaded
    # object so it sees the test bucket/region (test-only staleness fix).
    import consumer.storage_client as sc_module
    sc_module.settings = settings_module.settings
    with mock_aws():
        s3 = boto3.client("s3", region_name=_REGION)
        s3.create_bucket(
            Bucket=_BUCKET,
            CreateBucketConfiguration={"LocationConstraint": _REGION},
        )
        yield s3


def _list_keys(s3, prefix=""):
    resp = s3.list_objects_v2(Bucket=_BUCKET, Prefix=prefix)
    return [o["Key"] for o in resp.get("Contents", [])]


def test_upload_batch_writes_one_jsonl_object_under_raw_partition(s3_bucket):
    client = StorageClient(s3_client=s3_bucket)
    events = [{"event_id": "1", "device_id": "CAR-1"}, {"event_id": "2", "device_id": "CAR-2"}]

    key = client.upload_batch(events)

    assert key.startswith("raw/telemetry/year=")
    assert "/month=" in key and "/day=" in key and key.endswith(".jsonl")

    keys = _list_keys(s3_bucket, "raw/telemetry/")
    data_keys = [k for k in keys if not k.startswith("raw/telemetry/_dlq/")]
    assert data_keys == [key]

    body = s3_bucket.get_object(Bucket=_BUCKET, Key=key)["Body"].read().decode()
    lines = body.split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0])["event_id"] == "1"
    assert json.loads(lines[1])["device_id"] == "CAR-2"


def test_empty_batch_raises(s3_bucket):
    client = StorageClient(s3_client=s3_bucket)
    with pytest.raises(ValueError, match="empty"):
        client.upload_batch([])


def test_write_to_dlq_writes_single_json_under_dlq_partition(s3_bucket):
    client = StorageClient(s3_client=s3_bucket)

    key = client.write_to_dlq('{"bad": "json"', "ValidationError: missing event_id")

    assert key.startswith("raw/telemetry/_dlq/year=")
    assert key.endswith(".json")

    record = json.loads(s3_bucket.get_object(Bucket=_BUCKET, Key=key)["Body"].read())
    assert record["raw_body"] == '{"bad": "json"'
    assert "ValidationError" in record["error_reason"]
    assert "dlq_timestamp" in record


def test_dlq_and_raw_are_physically_isolated(s3_bucket):
    client = StorageClient(s3_client=s3_bucket)
    client.upload_batch([{"event_id": "1"}])
    client.write_to_dlq("garbage", "reason")

    raw = [k for k in _list_keys(s3_bucket, "raw/telemetry/") if "/_dlq/" not in k]
    dlq = _list_keys(s3_bucket, "raw/telemetry/_dlq/")
    assert len(raw) == 1
    assert len(dlq) == 1
