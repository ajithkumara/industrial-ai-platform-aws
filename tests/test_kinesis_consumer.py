"""
Unit tests for consumer/kinesis_consumer.py's on_record() handler.

AWS port of the Azure reference tests/test_eventhub_consumer.py. The P0-01
contract is IDENTICAL and is NOT weakened — only the transport metadata
changes (Event Hubs partition/offset -> Kinesis shard/SequenceNumber).

on_record() must:
  - Call batch_buffer.add(event, partition_id=shard_id, offset=seq,
    sequence_number=seq) for every valid record.
  - NOT checkpoint buffered records itself (BatchBuffer.flush does, after the
    durable S3 write).
  - Checkpoint immediately for DLQ records (write_to_dlq is synchronous).
  - NOT checkpoint when batch_buffer.add() raises (write failed).
"""

from __future__ import annotations

import json
import uuid

import pytest

import consumer.kinesis_consumer as consumer_module


class FakeCheckpointManager:
    def __init__(self):
        self.updates: list[dict] = []

    def update_checkpoint(self, partition_id, offset, sequence_number):
        self.updates.append(
            {"partition_id": partition_id, "offset": offset, "sequence_number": sequence_number}
        )


class FakeBatchBuffer:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.added: list[tuple] = []

    def add(self, event, partition_id, offset, sequence_number):
        if self.fail:
            raise RuntimeError("Simulated S3 write failure")
        self.added.append((event, partition_id, offset, sequence_number))


class FakeStorageClient:
    def __init__(self):
        self.dlq_writes: list[tuple[str, str]] = []

    def write_to_dlq(self, raw_body: str, error_reason: str) -> str:
        self.dlq_writes.append((raw_body, error_reason))
        return "raw/telemetry/_dlq/fake.json"


def _kinesis_record(body: dict, sequence_number="49590000000000000000000000000001"):
    return {
        "Data": json.dumps(body).encode("utf-8"),
        "SequenceNumber": sequence_number,
        "PartitionKey": body.get("device_id", "pk"),
    }


def _valid_body():
    return {
        "event_id": str(uuid.uuid4()),
        "device_id": "CAR-001",
        "asset_type": "vehicle",
        "timestamp": "2026-08-07T12:00:00+00:00",
        "priority": "normal",
        "schema_version": "1.0.0",
        "payload": {"speed_kmh": 42},
    }


@pytest.fixture(autouse=True)
def _restore_singletons():
    original = (
        consumer_module.checkpoint_manager,
        consumer_module.storage_client,
        consumer_module.batch_buffer,
    )
    yield
    (
        consumer_module.checkpoint_manager,
        consumer_module.storage_client,
        consumer_module.batch_buffer,
    ) = original


def test_valid_record_passed_to_buffer_with_shard_metadata(monkeypatch):
    fake_checkpoint = FakeCheckpointManager()
    fake_buffer = FakeBatchBuffer(fail=False)
    monkeypatch.setattr(consumer_module, "checkpoint_manager", fake_checkpoint)
    monkeypatch.setattr(consumer_module, "batch_buffer", fake_buffer)
    monkeypatch.setattr(consumer_module, "storage_client", FakeStorageClient())

    seq = "49590000000000000000000000000042"
    consumer_module.on_record("shardId-000000000000", _kinesis_record(_valid_body(), seq))

    assert len(fake_buffer.added) == 1
    _, partition_id, offset, sequence_number = fake_buffer.added[0]
    assert partition_id == "shardId-000000000000"
    assert offset == seq
    assert sequence_number == seq

    # P0-01: on_record must NOT checkpoint a buffered record.
    assert len(fake_checkpoint.updates) == 0, (
        "on_record advanced the checkpoint for a buffered record — this is the "
        "P0-01 bug. Checkpoint must only fire inside BatchBuffer.flush() after "
        "the durable S3 write."
    )


def test_failed_write_does_not_advance_checkpoint(monkeypatch):
    fake_checkpoint = FakeCheckpointManager()
    fake_buffer = FakeBatchBuffer(fail=True)
    monkeypatch.setattr(consumer_module, "checkpoint_manager", fake_checkpoint)
    monkeypatch.setattr(consumer_module, "batch_buffer", fake_buffer)
    monkeypatch.setattr(consumer_module, "storage_client", FakeStorageClient())

    consumer_module.on_record("shardId-000000000000", _kinesis_record(_valid_body()))
    assert len(fake_checkpoint.updates) == 0


def test_invalid_schema_routes_to_dlq_and_checkpoints(monkeypatch):
    fake_checkpoint = FakeCheckpointManager()
    fake_buffer = FakeBatchBuffer(fail=False)
    fake_storage = FakeStorageClient()
    monkeypatch.setattr(consumer_module, "checkpoint_manager", fake_checkpoint)
    monkeypatch.setattr(consumer_module, "batch_buffer", fake_buffer)
    monkeypatch.setattr(consumer_module, "storage_client", fake_storage)

    bad_body = {"device_id": "CAR-001"}  # missing required envelope fields
    consumer_module.on_record("shardId-000000000000", _kinesis_record(bad_body))

    assert len(fake_storage.dlq_writes) == 1
    # DLQ path checkpoints immediately (synchronous durable write).
    assert len(fake_checkpoint.updates) == 1
    assert len(fake_buffer.added) == 0


def test_invalid_json_routes_to_dlq(monkeypatch):
    fake_checkpoint = FakeCheckpointManager()
    fake_storage = FakeStorageClient()
    monkeypatch.setattr(consumer_module, "checkpoint_manager", fake_checkpoint)
    monkeypatch.setattr(consumer_module, "batch_buffer", FakeBatchBuffer())
    monkeypatch.setattr(consumer_module, "storage_client", fake_storage)

    record = {"Data": b"{not valid json", "SequenceNumber": "1", "PartitionKey": "pk"}
    consumer_module.on_record("shardId-000000000000", record)

    assert len(fake_storage.dlq_writes) == 1
    assert len(fake_checkpoint.updates) == 1
