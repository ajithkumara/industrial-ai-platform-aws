# CONSUMER_BEHAVIOUR.md — Current Azure Platform

> Phase 0E deliverable. The exact runtime behaviour of the ingestion
> consumer, including the hardened checkpoint-ordering fix (P0-01). The AWS
> port MUST NOT regress this behaviour.

## Files

`consumer/eventhub_consumer.py`, `consumer/batch_buffer.py`,
`consumer/checkpoint.py`, `consumer/storage_client.py`.

## The intended pipeline (per event)

```
receive  ->  validate (Pydantic)  ->  buffer (in-memory only)
   ->  durable ADLS write (on batch full / flush)  ->  checkpoint
```

Checkpoint advances **only after** the durable write is confirmed. This is
the P0-01 correctness contract.

## Delivery semantics

- **At-least-once.** On crash + restart, events since the last *flushed*
  checkpoint are re-read from Event Hubs and re-written to ADLS.
- **Idempotent replay** via Silver deduplication by `event_id`.
- **Loss window: zero** for crashes after the last successful flush. A crash
  with buffered-but-unflushed events causes re-delivery on restart, NOT loss.
  (Before P0-01: those events were permanently lost.)

## on_event() flow (`eventhub_consumer.py`)

1. `event.body_as_str("UTF-8")`.
2. `TelemetryEvent.model_validate_json(body)`.
   - On `ValidationError` or `json.JSONDecodeError`: `storage_client.write_to_dlq(body, reason)`
     then `_checkpoint_event(...)` **immediately** — DLQ write is synchronous,
     so the record is durable before return; checkpointing right away is correct.
3. Domain-agnostic structured log (partition, asset_type, device, priority,
   first 8 chars of event_id).
4. `batch_buffer.add(event=record.model_dump(), partition_id, offset, sequence_number)`.
   - If `add()` raises (flush failed): log, **do NOT checkpoint**, return.
     Buffered events remain in memory for retry.
   - **No checkpoint call here** for buffered events — that is BatchBuffer's job.

## BatchBuffer (`batch_buffer.py`) — the P0-01 mechanism

- Constructor: `BatchBuffer(storage_client, checkpoint_fn=None)`.
  `checkpoint_fn(partition_id, offset, sequence_number)` is injected by
  `main()` as `_do_checkpoint`.
- Internal buffer holds tuples `(event_dict, partition_id, offset, sequence_number)`.
- `add(...)` appends; triggers `flush()` when `len >= settings.storage.raw_batch_size`
  (default `RAW_BATCH_SIZE=20`). A plain append NEVER checkpoints.
- `flush()`:
  1. `upload_batch(data_dicts)` FIRST (durable write). If it raises, the
     exception propagates, buffer is NOT cleared, checkpoint NOT advanced.
  2. After success: build last `(offset, seq)` **per partition**, call
     `checkpoint_fn` once per partition. A checkpoint failure is logged but
     non-fatal (data is already durable; worst case is re-read on restart).
  3. `self._buffer.clear()`.
- `pending_events()` returns buffer depth.
- Graceful shutdown (`KeyboardInterrupt` in `main()`) calls `batch_buffer.flush()`.

## Checkpoint store (`checkpoint.py`)

`FileCheckpointManager` — **local JSON file** (`local/checkpoints.json`),
`{partition_id: {offset, sequence_number}}`. Explicitly a local-dev
mechanism. On startup `main()` resumes partitions from stored offsets, else
`@latest`.

## Storage client (`storage_client.py`)

`StorageClient` → ADLS Gen2 via `DataLakeServiceClient.from_connection_string`.
- `upload_batch(events)` — writes JSONL to
  `raw/telemetry/year=/month=/day=/telemetry_<ts>_<uuid8>.jsonl` (date-partitioned).
- `write_to_dlq(raw_body, reason)` — writes a single JSON object to
  `raw/telemetry/_dlq/year=/month=/day=/dlq_<ts>_<uuid8>.json` with
  `{raw_body, error_reason, dlq_timestamp}`.
- Lazy construction: singletons built inside `main()` (not at import), so
  importing the module in CI/tests never opens an Azure connection.

## Failure handling summary

| Failure | Behaviour |
|---|---|
| Invalid schema / JSON | DLQ write + immediate checkpoint |
| ADLS write raises during flush | exception propagates; buffer retained; no checkpoint |
| Checkpoint write fails after durable write | logged, non-fatal; re-read on restart |
| Process crash mid-buffer | buffered events re-read from last checkpoint on restart |

## Contract tests that MUST be ported

`tests/test_batch_buffer.py` (7): flush-on-batch-size, failed-flush-retains-events,
no-checkpoint-on-partial-buffer, checkpoint-after-flush-with-last-offset-per-partition,
no-checkpoint-when-write-fails, explicit-flush-checkpoints.
`tests/test_eventhub_consumer.py` (3): valid-event-passed-with-partition-metadata
(and NOT checkpointed by on_event), failed-write-does-not-advance-checkpoint,
invalid-schema-routes-to-DLQ-and-still-advances-checkpoint.

## AWS impact

- `batch_buffer.py` — **copied verbatim** (pure Python, no cloud dependency;
  the `checkpoint_fn` callback contract is cloud-agnostic).
- `eventhub_consumer.py` → `kinesis_consumer.py` — **adapted.** Replace
  `EventHubConsumerClient` with a Kinesis consumer (KCL-style or
  `boto3` `get_records` loop). `partition_id` → Kinesis `shardId`; `offset`
  → sequence number. The validate→buffer→durable-write→checkpoint ordering
  and DLQ semantics are preserved unchanged.
- `checkpoint.py` — **adapted for production.** Local JSON stays for local
  dev; production checkpointing uses a DynamoDB lease table (the KCL-native
  mechanism) instead of local file. Do NOT copy local file checkpointing
  into production.
- `storage_client.py` → S3 via `boto3`; same JSONL layout, same date
  partitioning, same DLQ prefix. Classification: **AZURE-SPECIFIC
  (transport/storage) wrapping SHARED buffering/checkpoint-ordering logic.**
