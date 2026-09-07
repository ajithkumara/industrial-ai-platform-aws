# CURRENT_AZURE_DATA_FLOW.md — Current Azure Platform

> Phase 0B deliverable. The exact current data flow, corrected against source
> code (not assumed from the prompt's diagram).

## End-to-end flow

```
[Edge producers]                          [NATS bridge]                  [Cloud-side]
 vehicle_producer.py                    nats_bearing_bridge.py         score_escalations.py
   (synthetic vehicle)         (bearing_sensor / bearing_inference /     (cloud_validation
                                orchestrator_mode / context_snapshot)      events written
        |                                     |                            to same landing)
        +------------------+------------------+------------------+---------------+
                                       |
                          EventHubProducer.send_events()
                                       |
                                 Azure Event Hubs
                        (namespace ehns-*, hub "telemetryhub",
                         2 partitions, consumer group "bronze-loader",
                         7-day retention [P1-14])
                                       |
                        consumer/eventhub_consumer.py :: on_event
                                       |
                    Pydantic TelemetryEvent.model_validate_json
                          |                              |
                    (invalid)                        (valid)
                          |                              |
                    write_to_dlq()               BatchBuffer.add()
              raw/telemetry/_dlq/...        (buffer; flush at RAW_BATCH_SIZE=20)
                          |                              |
                    [checkpoint now]           StorageClient.upload_batch()
                                              ADLS Gen2: raw/telemetry/
                                              year=/month=/day=/*.jsonl
                                                          |
                                              [checkpoint after durable write]
                                                          |
                                    Databricks Auto Loader (cloudFiles, JSON)
                                        dlt/bronze/ingest_raw_events.py
                                     -> industrial_ai.bronze.telemetry_bronze
                                        (+ _source_file, _ingested_at from _metadata)
                                                          |
                              dlt/silver/clean_and_deduplicate.py
                        expectations (valid event_id/device_id/asset_type/timestamp,
                        TRIM<>''), dedup by event_id (latest _ingested_at)
                        -> industrial_ai.silver.cleaned_telemetry_events
                        -> industrial_ai.silver.quarantine_telemetry_events [P1-11]
                                                          |
                              dlt/silver/flatten_payloads.py  (CONFIG-DRIVEN)
                        one DLT table PER config/asset_types/*.yml
                        -> industrial_ai.silver.silver_<asset>_telemetry / *_results
                                                          |
                        +---------------------------------+----------------------------+
                        |                                                              |
             dlt/gold/asset_health_summary.py                      dlt/gold/bearing_ml_features.py
             (domain-agnostic daily KPIs)                          (leakage-safe ML dataset +
             -> industrial_ai.gold.asset_health_summary               *_quarantine)
                        |                                                              |
             Evidence Gold tables:                                        ML Jobs (non-DLT):
             mode_history, detection_performance,                 train_bearing_isolation_forest.py
             edge_autonomy, cloud_egress, escalation_efficacy     evaluate_bearing_model.py
                                                                  cloud_forest train/score
                                                                  -> industrial_ai.ml.<model> (MLflow/UC)
```

## Corrections vs the assumed diagram

- **Two ingress sources**, not one: synthetic `vehicle_producer` AND the
  `nats_bearing_bridge` (4 bridged asset types). A fifth asset type,
  `cloud_validation`, is produced **cloud-side** by `score_escalations.py`
  writing into the same ADLS landing path — it is NOT bridged from NATS.
- **DLQ checkpoints immediately** (synchronous write); buffered events
  checkpoint only after flush (P0-01).
- Silver is **two stages**: (1) `clean_and_deduplicate` envelope cleanup +
  dedup, (2) `flatten_payloads` config-driven per-asset flattening. Plus a
  quarantine table.
- Gold is **not one table**: one domain-agnostic health summary + a
  leakage-safe ML feature table + five research-evidence tables.
- ML training/eval/scoring runs as **standalone Databricks Jobs**, not in the
  DLT pipeline (they are plain PySpark, no `import dlt`).

## Landing path detail

Consumer writes JSONL to `raw/telemetry/` (from `RAW_FOLDER` default). The
DLT pipeline's `bronze_path` config points Auto Loader at that same
`abfss://datalake@<account>.dfs.core.windows.net/raw/telemetry/`.

## Storage layout (ADLS Gen2, account `st*`)

- Filesystem `datalake` — medallion data (raw/, bronze/silver/gold managed by UC).
- Filesystem `checkpoint` — reserved for consumer offset state (prevent_destroy).
- `raw/telemetry/_dlq/` — dead letter queue.

## AWS translation of the flow (preview)

Event Hubs → Kinesis Data Streams; ADLS `raw/telemetry/` → S3
`s3://<bucket>/raw/telemetry/`; Auto Loader cloudFiles(JSON) reads S3;
Bronze/Silver/Gold DLT unchanged; UC on AWS; MLflow on AWS. See
`docs/aws/AZURE_TO_AWS_MAPPING.md`.
