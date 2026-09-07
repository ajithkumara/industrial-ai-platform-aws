# AWS_PARITY_MATRIX.md

> Phase 1 deliverable. Every current capability, its AWS translation, the
> parity requirement, behavioural differences, tests required, and status.
> Classification: **MP** = MUST PRESERVE, **NT** = AWS-NATIVE TRANSLATION,
> **AI** = AWS-SPECIFIC IMPROVEMENT, **NA** = NOT APPLICABLE.
> Status here is PLANNED (Phase 0 milestone); implementation follows.

| # | Current capability | Current implementation | AWS equivalent | AWS impl required | Parity | Behavioural differences | Tests required | Class | Status |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Generic telemetry envelope | `shared/telemetry_event.py` Pydantic, extra=forbid, min_length=1 | same file | copy verbatim | exact | none | test_telemetry_event.py | MP | PLANNED |
| 2 | Config-driven asset onboarding | `config/asset_types/*.yml` + `dlt/common/helpers.py` | same | copy verbatim | exact | none | test_asset_type_config.py | MP | PLANNED |
| 3 | Domain-agnostic Silver flatten | `dlt/silver/flatten_payloads.py` | same | bronze_path via pipeline conf only | exact | none | test_asset_type_config.py | MP | PLANNED |
| 4 | Envelope cleanup + dedup + quarantine | `dlt/silver/clean_and_deduplicate.py` | same | verbatim | exact | none | test_data_quality_scenarios.py | MP | PLANNED |
| 5 | Event ingress bus | Azure Event Hubs | Kinesis Data Streams | new TF + producer | functional | partition→shard; offset→seq; 1MB record cap | Kinesis send/batching tests | NT | PLANNED |
| 6 | Consumer validate→buffer→durable-write→checkpoint | `eventhub_consumer.py` + `batch_buffer.py` | `kinesis_consumer.py` + same buffer | adapt consumer only | exact ordering | shardId vs partition_id | test_batch_buffer.py (verbatim) + test_kinesis_consumer.py | MP+NT | PLANNED |
| 7 | Checkpoint after durable write (P0-01) | injected checkpoint_fn, per-partition | same callback contract | verbatim buffer | exact | prod store = DynamoDB lease | test_batch_buffer.py | MP | PLANNED |
| 8 | Local dev checkpoint | `FileCheckpointManager` JSON | keep for dev | verbatim | exact | prod uses DynamoDB (do not ship file to prod) | — | MP+NT | PLANNED |
| 9 | Raw landing (JSONL, date-partitioned) | ADLS `raw/telemetry/…` | S3 `raw/telemetry/…` | S3 storage_client | exact layout | abfss→s3 URI | moto test_s3_storage_client | NT | PLANNED |
| 10 | Dead letter queue | ADLS `_dlq/` + immediate checkpoint | S3 `_dlq/` | S3 client | exact | none | test_eventhub_consumer→kinesis | MP+NT | PLANNED |
| 11 | Bronze Auto Loader | cloudFiles(JSON) on abfss | cloudFiles(JSON) on s3 | pipeline config | exact | s3 URI | bundle validate | NT | PLANNED |
| 12 | Leakage-safe ML feature dataset | `dlt/gold/bearing_ml_features.py` + `ml/feature_spec.py` | same | verbatim | exact | none | test_feature_spec.py | MP | PLANNED |
| 13 | Score/threshold methodology | `ml/bearing_model_common.py`, train/eval jobs | same | verbatim | exact | none | test_bearing_model_common.py, contract test | MP | PLANNED |
| 14 | CloudForest validation | `ml/cloud_forest/*` | same | s3 landing URI only | exact | s3 URI | (job) | MP+NT | PLANNED |
| 15 | Unity Catalog governance | Access Connector MI → abfss external location | IAM role → s3 external location | UC TF on AWS | functional | credential mechanism | TF validate | NT | PLANNED |
| 16 | MLflow model registry (UC 3-part) | `industrial_ai.ml.*` | same on AWS | none | exact | none | contract test | MP | PLANNED |
| 17 | Secrets management | Key Vault | Secrets Manager + KMS | new TF | functional | auth model | TF validate | NT | PLANNED |
| 18 | Storage versioning [P0-05] | ADLS blob versioning | S3 versioning | TF | exact intent | — | TF | NT | PLANNED |
| 19 | Destroy protection [P0-02] | prevent_destroy on storage/KV/fs | prevent_destroy on S3/secrets | TF lifecycle | exact | — | TF plan | MP | PLANNED |
| 20 | Storage lifecycle [P1-09] | ADLS cool/archive policy | S3 lifecycle IA/Glacier | TF | exact intent | tier names | TF | NT | PLANNED |
| 21 | Diagnostic logging [P0-03] | diagnostic settings → Log Analytics | CloudWatch log groups + metric filters | TF | functional | metric names | — | NT | PLANNED |
| 22 | Alerting [P1-13] | consumer-lag + write-failure alerts | CloudWatch alarms (GetRecords.IteratorAgeMs, S3 4xx/5xx) | TF | functional | metric source | — | NT | PLANNED |
| 23 | DLT/pipeline failure alert [P0-04] | job email_notifications + DLT notifications | same (Databricks) + CloudWatch | verbatim | exact | — | — | MP | PLANNED |
| 24 | Retention window [P1-14] | EH 7-day | Kinesis 168h | TF | exact | — | — | NT | PLANNED |
| 25 | CI: tests | `ci-cd.yml` pytest | same + boto3/moto | near-verbatim | exact | — | full suite | MP | PLANNED |
| 26 | CI: TF plan/apply + PR diff [P1-17] + smoke [P1-16] | `ci.yml` OIDC→Azure | OIDC→AWS IAM role, S3 backend | adapt | functional | auth | — | NT | PLANNED |
| 27 | CI: bundle validate (required check) | `databricks_deploy.yml` no-paths | same on AWS auth | adapt | exact | auth | — | NT | PLANNED |
| 28 | Delta OPTIMIZE/VACUUM [P1-10] | `maintenance.yml` + notebook | same | verbatim | exact | — | — | MP | PLANNED |
| 29 | MLflow artifact backup [P1-15] | `mlflow_backup.yml` → ADLS | → S3 | adapt path | exact intent | s3 | — | NT | PLANNED |
| 30 | Private networking | (implicit) | VPC + endpoints, no public data | new TF | — | AWS-native | — | AI | PLANNED |
| 31 | Encryption keys | platform-managed | KMS CMKs | new TF | — | AWS-native | — | AI | PLANNED |
| 32 | Audit trail | Activity log | CloudTrail | new TF | — | AWS-native | — | AI | PLANNED |
| 33 | Container registry + scan | (n/a) | ECR + image scan | new | — | AWS-native | — | AI | PLANNED |
| 34 | Resource Groups | RG per env | tags + account/region | — | — | no RG concept | — | NA | PLANNED |
| 35 | NATS bridge | `edge/nats_bearing_bridge.py` | same translate + Kinesis producer | adapt producer | exact translate | — | test_nats_bearing_bridge.py | MP+NT | PLANNED |
| 36 | Vehicle/edge simulator | `edge/vehicle_producer.py` | same + Kinesis producer | adapt | exact data | — | — | MP+NT | PLANNED |

## Parity principles

- **Every MP row must be provably identical** — enforced by porting the
  exact contract test.
- **Every NT row documents the one behavioural difference** and why it is
  legitimate (cloud-native, not a downgrade).
- **AI rows add capability the Azure repo lacks** (VPC/KMS/CloudTrail/ECR) —
  they must not alter application behaviour.
- **NA rows** (Resource Groups) are explicitly out of scope with rationale.
