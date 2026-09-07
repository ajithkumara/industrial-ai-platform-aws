"""
Amazon Kinesis Consumer Application

AWS-native translation of the Azure reference
`consumer/eventhub_consumer.py`. Receives domain-agnostic telemetry from a
Kinesis Data Stream, validates each record with Pydantic, routes invalid
records to a Dead Letter Queue (DLQ) on S3, and writes valid records to the
S3 raw/Bronze prefix via BatchBuffer.

P0-01 invariant (PRESERVED EXACTLY — see batch_buffer.py)
=========================================================
The checkpoint is advanced ONLY after a batch is durably written to S3, once
per shard, using the last sequence number in the flushed batch. on_record()
never checkpoints buffered records. DLQ records checkpoint immediately
because write_to_dlq() is synchronous (the S3 object is durable before
on_record returns).

Azure → AWS mapping of concepts
-------------------------------
  Event Hubs partition        -> Kinesis shard        (partition_id = shard_id)
  Event Hubs offset           -> Kinesis SequenceNumber
  Blob/local checkpoint store -> DynamoDB lease (prod) / local file (dev)

Delivery semantics (unchanged): at-least-once. On crash + restart, records
since the last flushed checkpoint are re-read per shard and re-written to S3;
Silver deduplication by event_id makes replay idempotent. Loss window is zero
for crashes after the last successful flush.

Ordering: Kinesis guarantees order WITHIN a shard (as Event Hubs does within a
partition). Records are polled per shard and processed in sequence.

Backpressure / throttling: get_records is bounded by `Limit`; on
ProvisionedThroughputExceededException the poll loop backs off. A full-scale
deployment would use the Kinesis Client Library (KCL) with enhanced fan-out;
this boto3 poll loop is the reference implementation and is fully testable
with moto.
"""

from __future__ import annotations

import json
import logging
import time

import boto3
from pydantic import ValidationError

from config.settings import (
    CHECKPOINT_FILE,
    settings,
    validate_settings,
)
from .batch_buffer import BatchBuffer
from .checkpoint import FileCheckpointManager
from .storage_client import StorageClient
from shared.telemetry_event import TelemetryEvent
from shared.logger import setup_logger

logger = setup_logger("kinesis_consumer")

# Module-level singletons — constructed lazily inside main() (after
# validate_settings), never at import time, so importing this module in CI /
# tests never opens an AWS connection. Same pattern as the Azure reference.
checkpoint_manager = None
storage_client: StorageClient | None = None
batch_buffer: BatchBuffer | None = None

# Poll tuning (backpressure). Conservative defaults; override via env if needed.
_GET_RECORDS_LIMIT = 500
_EMPTY_POLL_SLEEP_S = 1.0
_THROTTLE_BACKOFF_S = 2.0


# ---------------------------------------------------------------------------
# Checkpoint callback (injected into BatchBuffer — P0-01)
# ---------------------------------------------------------------------------

def _do_checkpoint(partition_id: str, offset: str, sequence_number) -> None:
    """
    Called by BatchBuffer.flush() after a batch is durably written to S3.
    The ONLY place shard checkpoints advance for buffered records.
    """
    checkpoint_manager.update_checkpoint(
        partition_id=partition_id,
        offset=offset,
        sequence_number=sequence_number,
    )


# ---------------------------------------------------------------------------
# Record handler
# ---------------------------------------------------------------------------

def on_record(shard_id: str, record: dict) -> None:
    """
    Handle one Kinesis record.

    `record` is a Kinesis record dict with keys Data (bytes), SequenceNumber
    (str), PartitionKey (str). Mirrors on_event() in the Azure reference.
    """
    sequence_number = record["SequenceNumber"]
    data = record["Data"]
    event_body = data.decode("UTF-8") if isinstance(data, (bytes, bytearray)) else str(data)

    # 1. SCHEMA VALIDATION (the enterprise contract)
    try:
        rec = TelemetryEvent.model_validate_json(event_body)
    except ValidationError as ve:
        logger.warning("Schema validation failed. Routing to DLQ. Error: %s", ve)
        storage_client.write_to_dlq(event_body, str(ve))
        _checkpoint_record(shard_id, sequence_number)
        return
    except json.JSONDecodeError as je:
        logger.warning("Invalid JSON. Routing to DLQ. Error: %s", je)
        storage_client.write_to_dlq(event_body, str(je))
        _checkpoint_record(shard_id, sequence_number)
        return

    # 2. DOMAIN-AGNOSTIC LOGGING
    logger.info(
        "Received record | Shard: %s | Asset: %s | Device: %s | Priority: %s | EventID: %s",
        shard_id, rec.asset_type, rec.device_id, rec.priority, rec.event_id[:8],
    )

    # 3. BUFFER FOR BRONZE (S3)
    # P0-01: the shard + sequence number are stored alongside the event so
    # BatchBuffer can checkpoint the last sequence per shard AFTER the durable
    # write. on_record does NOT checkpoint buffered records.
    try:
        batch_buffer.add(
            event=rec.model_dump(),
            partition_id=shard_id,
            offset=sequence_number,
            sequence_number=sequence_number,
        )
    except Exception as e:  # noqa: BLE001
        logger.error(
            "Failed to persist buffered batch while adding record %s: %s. "
            "Checkpoint will NOT advance; buffered records remain in-memory "
            "for retry on the next flush.",
            rec.event_id, e,
        )
        return
    # No checkpoint here — BatchBuffer.flush() issues it after the durable write.


def _checkpoint_record(shard_id: str, sequence_number: str) -> None:
    """Advance the checkpoint for a single record already durable (DLQ / shutdown)."""
    checkpoint_manager.update_checkpoint(
        partition_id=shard_id,
        offset=sequence_number,
        sequence_number=sequence_number,
    )


# ---------------------------------------------------------------------------
# Shard iterator helper
# ---------------------------------------------------------------------------

def _shard_iterator(kinesis, stream_name: str, shard_id: str) -> str:
    """
    Resume from the last checkpointed sequence number for this shard, else
    start at LATEST (new records only). Use TRIM_HORIZON only for a full replay.
    """
    cp = checkpoint_manager.get_checkpoint(shard_id)
    if cp and cp.get("sequence_number"):
        resp = kinesis.get_shard_iterator(
            StreamName=stream_name,
            ShardId=shard_id,
            ShardIteratorType="AFTER_SEQUENCE_NUMBER",
            StartingSequenceNumber=cp["sequence_number"],
        )
        logger.info("Resuming shard %s after sequence %s", shard_id, cp["sequence_number"])
    else:
        resp = kinesis.get_shard_iterator(
            StreamName=stream_name, ShardId=shard_id, ShardIteratorType="LATEST"
        )
        logger.info("No checkpoint for shard %s. Starting at LATEST.", shard_id)
    return resp["ShardIterator"]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    validate_settings()

    global checkpoint_manager, storage_client, batch_buffer

    # Production uses the DynamoDB lease table; local dev uses the JSON file.
    if settings.checkpoint.table_name:
        from .dynamo_checkpoint import DynamoCheckpointManager
        checkpoint_manager = DynamoCheckpointManager(
            table_name=settings.checkpoint.table_name,
            region=settings.checkpoint.region,
        )
        logger.info("Using DynamoDB checkpoint table '%s'.", settings.checkpoint.table_name)
    else:
        checkpoint_manager = FileCheckpointManager(CHECKPOINT_FILE)
        logger.info("Using local file checkpoint '%s' (dev only).", CHECKPOINT_FILE)

    storage_client = StorageClient()
    batch_buffer = BatchBuffer(storage_client, checkpoint_fn=_do_checkpoint)

    stream_name = settings.kinesis.stream_name
    logger.info("Starting Kinesis consumer for stream '%s'...", stream_name)

    kinesis = boto3.client("kinesis", region_name=settings.kinesis.region)

    shards = kinesis.describe_stream(StreamName=stream_name)["StreamDescription"]["Shards"]
    iterators = {s["ShardId"]: _shard_iterator(kinesis, stream_name, s["ShardId"]) for s in shards}

    try:
        while True:
            for shard_id, it in list(iterators.items()):
                if it is None:
                    continue
                try:
                    resp = kinesis.get_records(ShardIterator=it, Limit=_GET_RECORDS_LIMIT)
                except kinesis.exceptions.ProvisionedThroughputExceededException:
                    logger.warning("Throttled on shard %s; backing off %.1fs", shard_id, _THROTTLE_BACKOFF_S)
                    time.sleep(_THROTTLE_BACKOFF_S)
                    continue

                for record in resp.get("Records", []):
                    on_record(shard_id, record)

                iterators[shard_id] = resp.get("NextShardIterator")
                if not resp.get("Records"):
                    time.sleep(_EMPTY_POLL_SLEEP_S)
    except KeyboardInterrupt:
        logger.info("Consumer stopped by user. Flushing buffered records...")
        batch_buffer.flush()  # flush() checkpoints after the durable write
    except Exception as e:  # noqa: BLE001
        logger.error("Consumer error: %s", e)


if __name__ == "__main__":
    main()
