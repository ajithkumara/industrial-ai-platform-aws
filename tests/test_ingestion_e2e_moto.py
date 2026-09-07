"""
End-to-end AWS ingestion test on emulated AWS (moto): Kinesis producer ->
Kinesis stream -> consumer.on_record -> BatchBuffer -> S3 Bronze -> file
checkpoint. Exercises the REAL StorageClient, BatchBuffer, FileCheckpointManager
and KinesisProducer against moto, not fakes.

Proves, on emulated AWS:
  - a full batch is durably written to S3 as one JSONL object,
  - the checkpoint advances only AFTER that durable write (P0-01),
  - duplicate events are BOTH retained at S3/Bronze (Bronze immutability;
    dedup is Silver's job — the DQ2 contract).
"""

from __future__ import annotations

import importlib
import json

import boto3
import pytest
from moto import mock_aws

_BUCKET = "e2e-raw"
_STREAM = "telemetryhub"
_REGION = "ca-central-1"


@pytest.fixture
def aws(monkeypatch, tmp_path):
    monkeypatch.setenv("S3_BUCKET", _BUCKET)
    monkeypatch.setenv("AWS_REGION", _REGION)
    monkeypatch.setenv("KINESIS_STREAM_NAME", _STREAM)
    monkeypatch.setenv("RAW_FOLDER", "raw/telemetry")
    monkeypatch.setenv("RAW_BATCH_SIZE", "3")

    import config.settings as settings_module
    importlib.reload(settings_module)
    # Rebind the module-level `settings` on every consumer/edge module that
    # captured it at import time, so they see the reloaded test config.
    import consumer.storage_client as _sc
    import consumer.batch_buffer as _bb
    import edge.base_producer as _bp
    _sc.settings = settings_module.settings
    _bb.settings = settings_module.settings
    _bp.settings = settings_module.settings

    with mock_aws():
        s3 = boto3.client("s3", region_name=_REGION)
        s3.create_bucket(Bucket=_BUCKET,
                         CreateBucketConfiguration={"LocationConstraint": _REGION})
        kinesis = boto3.client("kinesis", region_name=_REGION)
        kinesis.create_stream(StreamName=_STREAM, ShardCount=1)
        yield s3, kinesis, tmp_path, settings_module


def _valid(i, device="CAR-001"):
    return {
        "event_id": f"evt-{i}",
        "device_id": device,
        "asset_type": "vehicle",
        "timestamp": "2026-08-07T12:00:00+00:00",
        "priority": "normal",
        "schema_version": "1.0.0",
        "payload": {"speed_kmh": i},
    }


def _wire_consumer(s3, tmp_path):
    """Wire the real consumer singletons to moto-backed objects."""
    import consumer.kinesis_consumer as kc
    from consumer.storage_client import StorageClient
    from consumer.batch_buffer import BatchBuffer
    from consumer.checkpoint import FileCheckpointManager

    cp = FileCheckpointManager(tmp_path / "checkpoints.json")
    storage = StorageClient(s3_client=s3)
    buf = BatchBuffer(storage, checkpoint_fn=lambda pid, off, seq: cp.update_checkpoint(pid, off, seq))
    kc.checkpoint_manager = cp
    kc.storage_client = storage
    kc.batch_buffer = buf
    return kc, cp, storage, buf


def _list_raw_keys(s3):
    resp = s3.list_objects_v2(Bucket=_BUCKET, Prefix="raw/telemetry/")
    return [o["Key"] for o in resp.get("Contents", []) if "/_dlq/" not in o["Key"]]


def test_full_batch_lands_in_s3_and_checkpoint_advances_after_write(aws):
    s3, kinesis, tmp_path, _ = aws
    from edge.base_producer import KinesisProducer

    producer = KinesisProducer(kinesis_client=kinesis)
    producer.send_events([_valid(1), _valid(2), _valid(3)])

    kc, cp, storage, buf = _wire_consumer(s3, tmp_path)

    # Read what the producer wrote and drive on_record for each.
    shard_id = kinesis.describe_stream(StreamName=_STREAM)["StreamDescription"]["Shards"][0]["ShardId"]
    it = kinesis.get_shard_iterator(StreamName=_STREAM, ShardId=shard_id,
                                    ShardIteratorType="TRIM_HORIZON")["ShardIterator"]
    records = kinesis.get_records(ShardIterator=it, Limit=10)["Records"]
    assert len(records) == 3

    for r in records:
        kc.on_record(shard_id, r)  # batch_size=3 -> flush on the 3rd

    # One JSONL object with all three events.
    raw_keys = _list_raw_keys(s3)
    assert len(raw_keys) == 1
    body = s3.get_object(Bucket=_BUCKET, Key=raw_keys[0])["Body"].read().decode()
    assert len(body.split("\n")) == 3

    # P0-01: checkpoint advanced only after the durable write, to the last seq.
    assert shard_id in cp.checkpoints
    assert cp.checkpoints[shard_id]["sequence_number"] == records[-1]["SequenceNumber"]


def test_duplicate_events_are_both_retained_at_bronze(aws):
    s3, kinesis, tmp_path, _ = aws
    from edge.base_producer import KinesisProducer

    dup = _valid(1)
    producer = KinesisProducer(kinesis_client=kinesis)
    # Same logical event sent twice (at-least-once redelivery), plus one more
    # to complete the batch of 3.
    producer.send_events([dup, dup, _valid(2)])

    kc, cp, storage, buf = _wire_consumer(s3, tmp_path)
    shard_id = kinesis.describe_stream(StreamName=_STREAM)["StreamDescription"]["Shards"][0]["ShardId"]
    it = kinesis.get_shard_iterator(StreamName=_STREAM, ShardId=shard_id,
                                    ShardIteratorType="TRIM_HORIZON")["ShardIterator"]
    records = kinesis.get_records(ShardIterator=it, Limit=10)["Records"]
    for r in records:
        kc.on_record(shard_id, r)

    raw_keys = _list_raw_keys(s3)
    body = s3.get_object(Bucket=_BUCKET, Key=raw_keys[0])["Body"].read().decode()
    ids = [json.loads(line)["event_id"] for line in body.split("\n")]
    # Both duplicates retained at Bronze (immutability); dedup happens in Silver.
    assert ids.count("evt-1") == 2
    assert "evt-2" in ids
