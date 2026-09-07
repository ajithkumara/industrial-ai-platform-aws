"""
Failure-engineering tests (Milestone 11) — controlled failure scenarios against
emulated AWS (moto) + the real consumer/storage/checkpoint code.

Proves the platform recovers predictably (not just the happy path), covering the
Phase 13 scenarios that are testable without a live cluster:

  - malformed JSON            -> routed to S3 DLQ, checkpoint advances
  - missing envelope fields   -> routed to S3 DLQ (schema gate), checkpoint advances
  - transient S3 write failure-> exception surfaced, checkpoint does NOT advance,
                                 buffered events retried on next flush (no loss)
  - checkpoint restart recovery -> a new consumer resumes AFTER the last
                                    committed sequence number (no re-processing
                                    of already-durable data)
  - DLQ replay                -> DLQ objects are readable/re-ingestable

Out-of-order, Kinesis throttling, and live Databricks/network failures require a
live environment and are documented NOT EXECUTED in docs/AWS_FAILURE_ENGINEERING.md.
"""

from __future__ import annotations

import importlib
import json

import boto3
import pytest
from moto import mock_aws

_BUCKET = "fail-raw"
_REGION = "ca-central-1"


@pytest.fixture
def aws(monkeypatch, tmp_path):
    monkeypatch.setenv("S3_BUCKET", _BUCKET)
    monkeypatch.setenv("AWS_REGION", _REGION)
    monkeypatch.setenv("RAW_FOLDER", "raw/telemetry")
    monkeypatch.setenv("RAW_BATCH_SIZE", "2")
    import config.settings as sm
    importlib.reload(sm)
    import consumer.storage_client as _sc
    import consumer.batch_buffer as _bb
    _sc.settings = sm.settings
    _bb.settings = sm.settings
    with mock_aws():
        s3 = boto3.client("s3", region_name=_REGION)
        s3.create_bucket(Bucket=_BUCKET, CreateBucketConfiguration={"LocationConstraint": _REGION})
        yield s3, tmp_path, sm


def _valid(i):
    return {
        "event_id": f"e{i}", "device_id": "CAR-1", "asset_type": "vehicle",
        "timestamp": "2026-08-07T12:00:00+00:00", "priority": "normal",
        "schema_version": "1.0.0", "payload": {"speed_kmh": i},
    }


def _record(body_dict_or_str, seq):
    data = body_dict_or_str if isinstance(body_dict_or_str, str) else json.dumps(body_dict_or_str)
    return {"Data": data.encode("utf-8"), "SequenceNumber": seq, "PartitionKey": "pk"}


def _wire(s3, tmp_path, storage=None):
    import consumer.kinesis_consumer as kc
    from consumer.storage_client import StorageClient
    from consumer.batch_buffer import BatchBuffer
    from consumer.checkpoint import FileCheckpointManager
    cp = FileCheckpointManager(tmp_path / "cp.json")
    storage = storage or StorageClient(s3_client=s3)
    buf = BatchBuffer(storage, checkpoint_fn=lambda p, o, s: cp.update_checkpoint(p, o, s))
    kc.checkpoint_manager, kc.storage_client, kc.batch_buffer = cp, storage, buf
    return kc, cp, storage, buf


def _dlq_keys(s3):
    r = s3.list_objects_v2(Bucket=_BUCKET, Prefix="raw/telemetry/_dlq/")
    return [o["Key"] for o in r.get("Contents", [])]


def test_malformed_json_routed_to_dlq_and_checkpoints(aws):
    s3, tmp_path, _ = aws
    kc, cp, storage, buf = _wire(s3, tmp_path)
    kc.on_record("shardId-0", _record("{not valid json", "10"))
    assert len(_dlq_keys(s3)) == 1
    assert cp.checkpoints["shardId-0"]["sequence_number"] == "10"


def test_missing_envelope_fields_routed_to_dlq(aws):
    s3, tmp_path, _ = aws
    kc, cp, storage, buf = _wire(s3, tmp_path)
    kc.on_record("shardId-0", _record({"device_id": "CAR-1"}, "11"))  # missing event_id etc.
    assert len(_dlq_keys(s3)) == 1
    assert cp.checkpoints["shardId-0"]["sequence_number"] == "11"


def test_transient_s3_write_failure_does_not_advance_checkpoint(aws):
    s3, tmp_path, _ = aws

    class FlakyStorage:
        """Wraps the real S3 client but fails the first upload_batch."""
        def __init__(self, real):
            self._real = real
            self._failed = False
        def upload_batch(self, events):
            if not self._failed:
                self._failed = True
                raise RuntimeError("transient S3 error")
            return self._real.upload_batch(events)
        def write_to_dlq(self, *a, **k):
            return self._real.write_to_dlq(*a, **k)

    from consumer.storage_client import StorageClient
    flaky = FlakyStorage(StorageClient(s3_client=s3))
    kc, cp, storage, buf = _wire(s3, tmp_path, storage=flaky)

    # RAW_BATCH_SIZE=2 -> flush on 2nd record; first flush raises (swallowed by
    # on_record), so no checkpoint and events stay buffered.
    kc.on_record("shardId-0", _record(_valid(1), "20"))
    kc.on_record("shardId-0", _record(_valid(2), "21"))  # flush raises internally
    assert "shardId-0" not in cp.checkpoints          # NO checkpoint on failed write
    assert buf.pending_events() == 2                  # events retained for retry

    # Retry: an explicit flush now succeeds and advances the checkpoint.
    buf.flush()
    assert cp.checkpoints["shardId-0"]["sequence_number"] == "21"
    assert buf.pending_events() == 0


def test_checkpoint_restart_recovery(aws):
    s3, tmp_path, _ = aws
    # First consumer processes a batch of 2 (flushes + checkpoints).
    kc, cp, storage, buf = _wire(s3, tmp_path)
    kc.on_record("shardId-0", _record(_valid(1), "30"))
    kc.on_record("shardId-0", _record(_valid(2), "31"))
    assert cp.checkpoints["shardId-0"]["sequence_number"] == "31"

    # Simulate a restart: a brand-new checkpoint manager reads the committed
    # offset from disk and resumes AFTER it.
    from consumer.checkpoint import FileCheckpointManager
    cp2 = FileCheckpointManager(tmp_path / "cp.json")
    assert cp2.get_checkpoint("shardId-0")["sequence_number"] == "31"
    assert cp2.get_starting_position("shardId-0") == "31"  # AFTER_SEQUENCE_NUMBER resume point


def test_dlq_records_are_replayable(aws):
    s3, tmp_path, _ = aws
    kc, cp, storage, buf = _wire(s3, tmp_path)
    kc.on_record("shardId-0", _record("{bad", "40"))
    key = _dlq_keys(s3)[0]
    rec = json.loads(s3.get_object(Bucket=_BUCKET, Key=key)["Body"].read())
    # DLQ record preserves the raw body + reason -> operator can fix + replay.
    assert rec["raw_body"] == "{bad"
    assert "error_reason" in rec and "dlq_timestamp" in rec
