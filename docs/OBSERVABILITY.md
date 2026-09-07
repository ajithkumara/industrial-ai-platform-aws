# OBSERVABILITY.md — Milestone 10

> HEALTH SIGNAL → METRIC → ALARM → LOG → RUNBOOK for every critical component.
> Every alarm corresponds to a metric that is actually emitted (Kinesis service
> metrics, or a custom metric the consumer publishes) — no fake metrics.

## The 12 operational questions (and where each is answered)

| Question | Signal / location |
|---|---|
| Did ingestion receive the event? | Kinesis `IncomingRecords` (CloudWatch) |
| Was it persisted? | S3 object under `raw/telemetry/…`; consumer log line |
| Was it deduplicated? | Silver `cleaned_telemetry_events` row count vs Bronze |
| Was it quarantined? | S3 `_dlq/…` (envelope) + `silver.quarantine_telemetry_events` (DQ) |
| Did Silver process it? | DLT event log; Silver table |
| Did Gold process it? | DLT event log; Gold tables |
| Which model processed it? | `model_version` / `cloud_model_version` columns |
| Which threshold was used? | MLflow run param `selected_threshold` (frozen artifact) |
| Was cloud inference invoked? | `cloud_validation` events; escalation_efficacy |
| Was escalation triggered? | `orchestrator_mode` / mode_history |
| How long did each stage take? | Kinesis IteratorAge; DLT latency; MLflow run duration |
| Where did it fail? | DLQ (ingest), quarantine (DQ), DLT event log (pipeline), job alert (ML) |

## Component signals

| Component | Health signal | Metric | Alarm | Log | Runbook |
|---|---|---|---|---|---|
| Ingestion (Kinesis) | consumer keeping up | `GetRecords.IteratorAgeMilliseconds` | `*-consumer-lag` > 60s/15m | consumer CloudWatch log group | RB-01 |
| Ingestion volume | events arriving | `IncomingRecords` | `*-no-incoming-records` < 1/15m | — | RB-02 |
| Data quality | DLQ volume | custom `IndustrialAI/DLQRecords` | `*-dlq-volume` > 0 | DLQ objects | RB-03 |
| Storage | write success | S3 4xx/5xx (StorageBlobLogs equiv.) | (add per-bucket) | S3 access logs | RB-03 |
| Pipeline | DLT update health | DLT event log ResultState | job email (P0-04) | DLT event log | RB-04 |
| ML | job success | job run state | job email (P0-04) | MLflow run | RB-04 |
| Audit | control-plane actions | CloudTrail | (GuardDuty optional) | CloudTrail S3 | RB-05 |
| Network | flows | VPC flow logs | (add anomaly) | flow log group | RB-05 |

## Custom metric contract

The consumer should publish `IndustrialAI/DLQRecords` (dimension
`Environment`) via `put_metric_data` whenever it routes to the DLQ. The
`*-dlq-volume` alarm consumes exactly that metric; until the consumer publishes
it, the alarm stays INSUFFICIENT_DATA (never falsely OK). Wiring this call into
`on_record`'s DLQ branch is tracked as backlog B-M10-METRIC (P1).

## Correlation IDs

`event_id` (envelope) is the end-to-end correlation key across DLQ, Bronze,
Silver, Gold, and evidence tables. `dataset_run_id` isolates an experiment's
data. MLflow `run_id` ties a model + frozen threshold to its evaluation.

## Runbooks (docs/runbooks/)

RB-01 consumer-lag, RB-03 dlq-volume — see docs/runbooks/OPERATIONS.md.
