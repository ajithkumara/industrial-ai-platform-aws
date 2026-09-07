# ingestion-evidence.md — Milestone 2 (AWS Ingestion)

> Executed evidence. Live-cloud steps that require a real AWS account are
> marked NOT EXECUTED with the exact command to run; everything else was run
> against emulated AWS (moto) and is real.

- **Date (UTC):** 2026-09-07T16:39:59Z
- **Commit (pre-commit):** parent ac8fbd8 (M1). This M2 work is staged for your commit.
- **Environment:** Python 3.10.12, Linux 6.8.0, pytest 9.x, moto 5.x, boto3 1.x

## What was implemented

| File | Role | Azure ref |
|---|---|---|
| consumer/storage_client.py | S3 raw/Bronze + DLQ writer (boto3) | ADLS DataLakeServiceClient |
| consumer/checkpoint.py | file checkpoint (dev), verbatim | same |
| consumer/dynamo_checkpoint.py | DynamoDB lease checkpoint (prod) | EH blob checkpoint store |
| consumer/kinesis_consumer.py | receive→validate→buffer→S3→checkpoint (P0-01) | eventhub_consumer.py |
| edge/base_producer.py | Kinesis PutRecords producer | EventHubProducer |
| edge/run_simulator.py, run_nats_bridge.py, vehicle_producer.py | entry points / generator | same (producer swapped) |

## E-M2-1 — Ingestion unit + integration tests (moto)

Command:
```
python3 -m pytest tests/test_storage_client_s3.py tests/test_dynamo_checkpoint.py \
                  tests/test_kinesis_consumer.py tests/test_ingestion_e2e_moto.py -v
```
Result: **14 passed.**

| Test | Proves |
|---|---|
| test_storage_client_s3 (4) | JSONL object under raw/telemetry/year=/month=/day=; empty batch raises; DLQ single-JSON under _dlq/; raw and DLQ physically isolated |
| test_dynamo_checkpoint (4) | update/get; default -1; **restart recovery** (new instance reads committed checkpoint); write failure non-fatal (at-least-once) |
| test_kinesis_consumer (4) | **P0-01**: valid record buffered with shard metadata + NOT checkpointed; failed write → no checkpoint; invalid schema → DLQ + immediate checkpoint; invalid JSON → DLQ |
| test_ingestion_e2e_moto (2) | **end-to-end on emulated AWS**: producer→Kinesis→on_record→BatchBuffer→S3; one JSONL object of 3 events; checkpoint advances only after durable write to last sequence number; **duplicate events both retained at Bronze** (DQ2 immutability, dedup deferred to Silver) |

## E-M2-2 — Full regression suite

Command: `python3 -m pytest tests/ -q`
Result: **143 passed, 11 skipped, 0 failed** (11 skips = CWRU real-.mat boundary tests, dataset absent — identical to Azure CI).

## E-M2-3 — Domain/cloud decoupling gate

Command: `grep -rlE "^\s*(import|from)\s+(boto3|botocore|azure)" shared/ config/ ml/ dlt/ consumer/batch_buffer.py`
Result: **zero matches.** boto3 appears only in the four boundary modules
(storage_client, dynamo_checkpoint, kinesis_consumer, base_producer).

## E-M2-4 — Static analysis + dependency scan

`python3 -m py_compile <all modules>` → OK.
`python3 -m pip_audit -r requirements.txt` → **No known vulnerabilities found.**

## AWS service decisions (per Phase 3 requirement)

**Kinesis Data Streams** — WHY: managed, shard-ordered streaming bus matching
Event Hubs' partition-ordered semantics. ALTERNATIVES: MSK (Kafka — heavier
ops, needed only for Kafka-API compatibility), SQS (no ordering/replay).
FAILURE MODES: ProvisionedThroughputExceeded (handled: backoff), shard limits.
COST: per-shard-hour + per-million-PUT; dev = 1 shard.

**S3** — WHY: durable immutable object store for raw/Bronze JSONL; native
Databricks Auto Loader source. ALTERNATIVES: EFS (POSIX, costlier, unneeded).
FAILURE MODES: throttling (retry), eventual list consistency (mitigated by
unique keys). COST: storage + PUT + lifecycle to IA/Glacier (M3).

**DynamoDB (checkpoint lease)** — WHY: KCL-native, durable, shared checkpoint
store surviving task replacement/rebalance. ALTERNATIVES: local file (dev
only — not durable/shared), S3 (no conditional-write lease semantics).
FAILURE MODES: write failure (handled non-fatally; at-least-once). COST:
on-demand, trivial at checkpoint cadence.

## NOT EXECUTED (require your AWS account)

| Step | Command (for you to run) | Why deferred |
|---|---|---|
| Live stream create + produce | `aws kinesis create-stream --stream-name telemetryhub --shard-count 1` then run `python -m edge.run_simulator` | needs AWS creds; provisioned in M4 Terraform |
| Live consume → S3 | `python -m consumer.kinesis_consumer` against real stream/bucket | needs deployed infra (M4/M6) |
| Deployed-resource verification | `aws s3 ls s3://<bucket>/raw/telemetry/` | after M4 apply |

These are delivered deploy-ready; no cloud result is fabricated.
