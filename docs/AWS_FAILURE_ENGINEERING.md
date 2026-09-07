# AWS_FAILURE_ENGINEERING.md — Milestone 11

> Controlled failure scenarios and expected behaviour. Tested items run against
> emulated AWS (moto) + the real consumer/storage/checkpoint code. Live-only
> scenarios are marked NOT EXECUTED with how to inject them.

## Executed (tests/test_failure_recovery.py — 5 passed)

| Scenario | Expected behaviour | Result |
|---|---|---|
| Malformed JSON | Routed to S3 DLQ; checkpoint advances (record is un-processable, durable in DLQ) | PASS |
| Missing envelope fields | Schema gate → S3 DLQ; checkpoint advances | PASS |
| Transient S3 write failure | Exception surfaced; checkpoint does NOT advance; events retained in buffer; **retry succeeds with no loss** (P0-01) | PASS |
| Checkpoint restart recovery | New consumer instance reads committed sequence from the store and resumes AFTER it (no reprocessing of durable data) | PASS |
| DLQ replay | DLQ object preserves `raw_body` + `error_reason` + `dlq_timestamp` → operator can fix and re-ingest | PASS |

Duplicate-event handling (both retained at Bronze; dedup in Silver) is covered
in `tests/test_ingestion_e2e_moto.py` (M2).

## Expected behaviour (documented; NOT EXECUTED — need live AWS/Databricks)

| Scenario | Expected behaviour | How to inject |
|---|---|---|
| Kinesis throttling | `ProvisionedThroughputExceeded` → consumer backs off (`_THROTTLE_BACKOFF_S`) and retries; no loss | drive > shard throughput; observe GetRecords.IteratorAge alarm |
| Out-of-order records | Per-shard order preserved; cross-shard order not guaranteed (documented) — event-time in payload, not arrival order, drives correctness (DQ11) | multi-shard load |
| S3 outage | `put_object` raises → checkpoint not advanced → retry on recovery | fault injection / SCP deny |
| DynamoDB checkpoint failure | Non-fatal (data durable in S3); re-read on restart, Silver dedups | deny dynamodb:PutItem |
| Databricks job failure | P0-04 email alert; DLT pipeline halts update, retains Bronze | fail a job run |
| Deployment failure / rollback | `apply` fails → `environment: dev` gate + `needs: validate` blocks deploy; re-run previous good | break a plan |
| Consumer restart | Resume from DynamoDB lease (prod) / file (dev) after last committed sequence | kill + restart task |

## Invariants preserved under failure

- **At-least-once, zero loss after last flush** — checkpoint only advances after
  a durable S3 write (P0-01).
- **Idempotent replay** — Silver dedup by `event_id`.
- **Poison events isolated** — DLQ, never silently dropped.
