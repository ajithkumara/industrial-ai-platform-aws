# DATABRICKS_BEHAVIOUR.md — Current Azure Platform

> Phase 0F deliverable. The exact current Databricks pipeline, bundle, jobs
> and Unity Catalog behaviour.

## Bundle (`databricks.yml` at repo root)

- Bundle name `azure-industrial-ai-platform`. Bundle root is the **repo
  root** (moved from `databricks/` because `dlt/` and `config/asset_types/`
  are siblings of `databricks/` and DAB cannot reference files outside its
  root).
- Variables: `storage_account_name` (from TF output), `storage_container`
  (default `datalake`), `sql_warehouse_id` (default `""`, P1-12 dashboard).
- Targets: `dev` (default, mode development), `test` (development), `prod`
  (production).
- `include:` — the DLT pipeline (`resources/pipelines/*.yml`), plus the
  ACTIVE jobs: `cloud_forest.yml`, `bearing_isolation_forest.yml`,
  `maintenance.yml` (P1-10), `mlflow_backup.yml` (P1-15). The dashboard is
  intentionally excluded from validate (requires a real `warehouse_id`).
- `bronze.yml`, `silver.yml`, `gold.yml` are **deliberately NOT included** —
  they wrap DLT-dependent notebooks that cannot run as standalone Jobs and
  would create a second, uncoordinated execution path.
- Host resolved from `DATABRICKS_HOST` env / profile, never hardcoded.

## The one production pipeline (`resources/pipelines/dlt.yml`)

`industrial_ai_dlt_pipeline` — `catalog: industrial_ai`, `target: bronze`,
serverless, photon, `development: true`, `continuous: false`. P0-04
notifications on update/flow failure. Libraries (notebook order does not
matter — DLT builds the graph from `dlt.read()` calls):
- Bronze: `dlt/bronze/ingest_raw_events.py`
- Silver: `clean_and_deduplicate.py`, `flatten_payloads.py`
- Gold: `asset_health_summary.py`, `mode_history.py`, `detection_performance.py`,
  `edge_autonomy.py`, `cloud_egress.py`, `escalation_efficacy.py`, `bearing_ml_features.py`
- Configuration keys: `asset_types_config_dir`, `dlt_common_dir` (deployed
  absolute paths via `${workspace.file_path}`), `bronze_path` (ABFSS, from
  bundle vars), plus ABFS OAuth config forcing managed-identity auth.

## Medallion layers (behaviour)

### Bronze — `dlt/bronze/ingest_raw_events.py`
Auto Loader streaming: `spark.readStream.format("cloudFiles")`,
`cloudFiles.format=json`, `inferColumnTypes=true`, reads `bronze_path`.
Adds `_source_file = _metadata.file_path`, `_ingested_at =
_metadata.file_modification_time` (streaming file source needs `_metadata`,
not `input_file_name()`). Table `telemetry_bronze`.

### Silver stage 1 — `clean_and_deduplicate.py`
`@dlt.expect_or_drop` on the four identity fields (with `TRIM(...) <> ''`),
`to_timestamp(timestamp)`, dedup by `event_id` keeping latest `_ingested_at`
via a `row_number()` window. Produces
`industrial_ai.silver.cleaned_telemetry_events`. P1-11 quarantine table
`quarantine_telemetry_events` captures the exact complement with a
`_quarantine_reason` array.

### Silver stage 2 — `flatten_payloads.py` (CONFIG-DRIVEN, domain-agnostic)
Loads `dlt/common/helpers.py` **by file path** (not package import — the DLT
runtime injects its own `dlt` module and would collide). For every
`config/asset_types/*.yml`, dynamically registers one DLT table that reads
`cleaned_telemetry_events`, filters `asset_type`, casts configured
`payload.<source>` fields to their declared Spark types aliased to targets,
writes `industrial_ai.silver.<silver_table>`. A configured source path
absent from the inferred schema becomes a typed `NULL` column (so a type can
be onboarded ahead of its data — `_source_path_exists`). Malformed config
raises `AssetTypeConfigError` at pipeline-definition time.

### Gold
- `asset_health_summary.py` — domain-agnostic daily per-asset_type/device
  KPIs (total_events, last_seen, critical/high counts).
- `bearing_ml_features.py` — leakage-safe ML dataset (see ML_BEHAVIOUR.md):
  recording-level stratified split, backward-only trend features,
  quarantine-not-NULL, `@dlt.expect_or_fail`. Plus `_quarantine` table.
- Five evidence tables: `mode_history`, `detection_performance`,
  `edge_autonomy`, `cloud_egress`, `escalation_efficacy`.

## Jobs (non-DLT, `resources/jobs/`)

- `cloud_forest.yml` — `cloud_forest_train` (manual), `cloud_forest_score_escalations`
  (every 15 min). Serverless. P0-04 alerts.
- `bearing_isolation_forest.yml` — `..._train` (manual), `..._evaluate`
  (manual, requires explicit `train_run_id`). Serverless env with
  scikit-learn + mlflow. P0-04 alerts.
- `maintenance.yml` (P1-10) — weekly OPTIMIZE + VACUUM.
- `mlflow_backup.yml` (P1-15) — daily model artifact backup to ADLS.

## Unity Catalog (provisioned by `terraform/modules/databricks/unity_catalog.tf`)

Storage credential (Access Connector managed identity) → external location
`industrial_ai_lake` (abfss datalake) → catalog `industrial_ai` → schemas
`bronze, silver, gold, serving, ml`. Least-privilege grants. The `ml` schema
is required for three-part model registration `industrial_ai.ml.<model>`.

## Contract behaviours that MUST be preserved

Single production DLT path; config-driven flatten with no `if asset_type`
branches; two-defence DQ; leakage-safe ML features; quarantine-not-NULL;
training/eval as separate manual jobs.

## AWS impact

- **All DLT notebooks copy verbatim** — pure PySpark + DLT, no Azure API
  calls. Only two things change:
  1. `bronze_path` ABFSS URI → S3 URI (`s3://<bucket>/raw/telemetry/`), and
     the ABFS OAuth config block → S3/instance-profile config (or UC
     external location credential on AWS — usually nothing in the notebook).
  2. `databricks.yml` variables (`storage_account_name` → `s3_bucket`).
- `databricks.yml` bundle structure, targets, includes — **preserved.**
- Jobs YAML — **preserved** (serverless, same notebooks, same schedules).
- Unity Catalog — **adapted**: storage credential uses an AWS IAM role
  (instance profile / UC storage credential for S3) instead of Azure Access
  Connector; external location URL becomes `s3://...`. Catalog/schema/grants
  identical. Classification: **DATABRICKS-SPECIFIC (portable) + thin
  AWS-native storage/identity swap.**
