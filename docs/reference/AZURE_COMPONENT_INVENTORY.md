# AZURE_COMPONENT_INVENTORY.md — Current Azure Platform

> Phase 0A deliverable. Every significant component of the CURRENT repo,
> based on actual source. Classification legend: **SHARED** (cloud-free
> logic), **AZURE** (Azure-specific), **DBX** (Databricks-specific, portable),
> **DOMAIN-AGNOSTIC**, **DOMAIN-SPECIFIC**, **LEGACY**, **ROADMAP**.

## shared/

| Path | Purpose | Deps | Class | Tests |
|---|---|---|---|---|
| `shared/telemetry_event.py` | Generic Envelope (Pydantic) | pydantic | SHARED / DOMAIN-AGNOSTIC | test_telemetry_event.py |
| `shared/config.py` | `load_config(env)` YAML loader | pyyaml | SHARED | — |
| `shared/logger.py` | `setup_logger` console/file | stdlib | SHARED | — |
| `shared/constants.py` | Medallion stage names | — | SHARED | — |
| `shared/schemas.py`, `shared/helpers.py` | stubs | — | LEGACY | — |

## config/

| Path | Purpose | Deps | Class | Tests |
|---|---|---|---|---|
| `config/settings.py` | Frozen dataclass settings from `.env`; lazy `validate_settings()` | dotenv | AZURE (EH/ADLS) + SHARED shape | test_settings_module.py |
| `config/logging.py` | basicConfig | stdlib | SHARED | — |
| `config/environments/{dev,test,prod}.yaml` | env config-as-code | — | AZURE (names) | — |
| `config/asset_types/*.yml` (8) | Config-driven asset-type field mappings | — | DOMAIN-AGNOSTIC | test_asset_type_config.py |

## consumer/

| Path | Purpose | Inputs | Outputs | State | Failure | Class | Tests |
|---|---|---|---|---|---|---|---|
| `eventhub_consumer.py` | EH receive → validate → DLQ/buffer; injects checkpoint_fn | EH events | ADLS batches, DLQ, checkpoints | checkpoints.json | DLQ on invalid; no-checkpoint on failed write | AZURE (transport) | test_eventhub_consumer.py |
| `batch_buffer.py` | Buffer + flush + per-partition checkpoint after durable write (P0-01) | events+partition meta | upload_batch calls, checkpoint_fn | in-memory buffer | flush raises → retain+no-checkpoint | SHARED | test_batch_buffer.py |
| `checkpoint.py` | `FileCheckpointManager` local JSON | offsets | checkpoints.json | file | logs on IO error | AZURE-dev / SHARED | (indirect) |
| `storage_client.py` | ADLS Gen2 JSONL upload + DLQ | events | ADLS files | — | raises on write fail | AZURE | (fakes) |

## edge/

| Path | Purpose | Class | Tests |
|---|---|---|---|
| `base_producer.py` | `EventHubProducer` send_batch | AZURE | — |
| `vehicle_producer.py` | Synthetic vehicle telemetry generator | SHARED (generator) / DOMAIN-SPECIFIC data | — |
| `industrial_producer.py` | stub | ROADMAP | — |
| `nats_bearing_bridge.py` | NATS→EH bridge, 4 asset types, deterministic uuid5, context sampling | SHARED (translate) + AZURE (producer) | test_nats_bearing_bridge.py |
| `run_simulator.py`, `run_nats_bridge.py` | entry points | AZURE | — |

## dlt/

| Path | Purpose | Class | Tests |
|---|---|---|---|
| `bronze/ingest_raw_events.py` | Auto Loader cloudFiles JSON → telemetry_bronze (+_metadata) | DBX (S3 URI swap) | — |
| `silver/clean_and_deduplicate.py` | expectations + dedup + quarantine | DBX / DOMAIN-AGNOSTIC | test_data_quality_scenarios.py |
| `silver/flatten_payloads.py` | Config-driven per-asset flatten (no branches) | DBX / DOMAIN-AGNOSTIC | test_asset_type_config.py |
| `common/helpers.py` | asset-type loader/discovery/validation, SPARK_TYPE_MAP | SHARED | test_asset_type_config.py |
| `common/expectations.py`, `common/schemas.py` | stubs | LEGACY | — |
| `gold/asset_health_summary.py` | domain-agnostic daily KPIs | DBX / DOMAIN-AGNOSTIC | — |
| `gold/bearing_ml_features.py` | leakage-safe ML dataset + quarantine | DBX / DOMAIN-SPECIFIC(bearing) | test_feature_spec.py |
| `gold/{mode_history,detection_performance,edge_autonomy,cloud_egress,escalation_efficacy}.py` | research evidence tables | DBX / DOMAIN-SPECIFIC | (research) |
| `gold/predictive_features.py` | (present) | DBX | — |

## ml/

| Path | Purpose | Class | Tests |
|---|---|---|---|
| `feature_spec.py` | normative feature/split spec (pure) | SHARED | test_feature_spec.py |
| `bearing_model_common.py` | score transform + threshold selection (pure) | SHARED | test_bearing_model_common.py |
| `train_bearing_isolation_forest.py` | edge baseline train + freeze + register | DBX Job | test_train_..._contract.py |
| `evaluate_bearing_model.py` | one-time TEST eval | DBX Job | — |
| `cloud_forest/train_cloud_forest.py` | heavier cloud IF | DBX Job | — |
| `cloud_forest/score_escalations.py` | async escalation scoring → cloud_validation | DBX Job (S3 URI swap) | — |
| `cwru_loader.py` | real CWRU .mat → events (numpy/scipy) | SHARED | test_cwru_loader.py |
| `feature_store_setup.py`, `train_anomaly_model.py` | SUPERSEDED stubs | LEGACY | — |

## databricks/

| Path | Purpose | Class |
|---|---|---|
| `databricks.yml` (root) | DAB bundle: vars, targets dev/test/prod, includes | DBX (var swap) |
| `resources/pipelines/dlt.yml` | the one production DLT pipeline | DBX (bronze_path swap) |
| `resources/jobs/{cloud_forest,bearing_isolation_forest,maintenance,mlflow_backup}.yml` | active jobs | DBX |
| `resources/jobs/{bronze,silver,gold}.yml` | reference-only, excluded | DBX / LEGACY |
| `resources/dashboards/ops_dashboard.yml` | P1-12 ops dashboard (excluded from validate) | DBX |
| `sql/*.sql`, `notebooks/SQL-Workbook.py` | catalog/grants/schemas SQL | DBX |

## terraform/  (see TERRAFORM_COMPONENT_MAPPING.md for detail)

`bootstrap/`, `environments/{dev,test,prod}/`, `modules/{resource_group,
storage,eventhub,access_connector,rbac,keyvault,databricks,monitoring,
unity_catalog}/`, `unity_catalog/dev/`. Class: **AZURE — full translation.**

## monitoring/

| Path | Purpose | Class |
|---|---|---|
| `monitoring/alert_rules.json` | alert rule definitions | AZURE (→ CloudWatch) |

## .github/workflows/  (see CICD_BEHAVIOUR.md)

`ci.yml`, `terraform.yml`, `databricks_deploy.yml`, `ci-cd.yml`. Class:
**AZURE auth (→ AWS OIDC); workflow philosophy preserved.**

## scripts/ & tests/

`scripts/backup_before_subscription_expiry.ps1` (AZURE ops), `scripts/utils.py`.
`tests/` — see TEST_COVERAGE_MAP.md.

## docs/ (existing in Azure repo)

`docs/architecture/`, `docs/runbooks/` (CLOUD_ACCEPTANCE_RUNBOOK,
NEW_SUBSCRIPTION_REDEPLOYMENT, SP_SECRET_ROTATION), `docs/deployment/`,
`docs/disaster-recovery.md`, `docs/verification/`, `docs/thesis/`. Class:
reference; AWS repo gets its own `docs/aws/` + `docs/reference/` (this set).

## Summary counts

- **Copied verbatim (SHARED/DBX cloud-free):** shared/telemetry_event.py,
  config/asset_types/*, dlt/common/helpers.py, all dlt/* notebooks,
  ml/feature_spec.py, ml/bearing_model_common.py, ml/cwru_loader.py,
  consumer/batch_buffer.py, edge translate logic, all pure-Python tests.
- **Adapted (AZURE→AWS):** config/settings.py, config/environments/*,
  consumer/eventhub_consumer.py→kinesis, checkpoint.py (prod), storage_client.py→S3,
  edge base_producer→kinesis, all terraform, all CI auth, monitoring.
- **New AWS-native:** VPC, KMS, ECR, CloudTrail, S3 backend + DynamoDB lock,
  Kinesis consumer checkpoint (DynamoDB lease).
- **Legacy/superseded (do not port):** feature_store_setup.py,
  train_anomaly_model.py, shared/schemas.py, shared/helpers.py stubs,
  dlt/common/expectations.py + schemas.py stubs.
