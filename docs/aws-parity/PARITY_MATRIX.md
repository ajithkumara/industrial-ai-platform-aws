# PARITY_MATRIX.md

> 5-state parity tracking. States are strictly ordered and never conflated:
> **SPECIFIED** (Phase 0 doc exists) → **NOT YET IMPLEMENTED** → **IMPLEMENTED**
> (code exists) → **VERIFIED** (a test was actually executed and passed) →
> **HARDENED** (production controls + failure tests in place).
>
> As of this iteration only Milestone 1 has been implemented. Everything else
> is SPECIFIED / NOT YET IMPLEMENTED. This file is updated with executed
> evidence after each milestone gate; see `TEST_EVIDENCE.md`.

## Legend
`SPEC` specified · `NYI` not yet implemented · `IMPL` implemented ·
`VERIF` verified by executed test · `HARD` hardened

## Capability matrix

| Area | Capability | Azure ref | AWS target | State | Evidence |
|---|---|---|---|---|---|
| **Domain core** | Generic envelope | shared/telemetry_event.py | same (verbatim) | **VERIF** (M1) | TEST_EVIDENCE §M1 |
| Domain core | Config-driven asset types | config/asset_types + dlt/common/helpers | same (verbatim) | **VERIF** (M1) | TEST_EVIDENCE §M1 |
| Domain core | Batch buffer + checkpoint ordering (P0-01) | consumer/batch_buffer.py | same (verbatim, docstring cloud-neutral) | **VERIF** (M1) | TEST_EVIDENCE §M1 |
| Domain core | ML feature spec / split policy | ml/feature_spec.py + dlt/gold/bearing_ml_features.py | same (verbatim) | **VERIF** (M1) | TEST_EVIDENCE §M1 |
| Domain core | Score/threshold logic | ml/bearing_model_common.py | same (verbatim) | **VERIF** (M1) | TEST_EVIDENCE §M1 |
| Domain core | CWRU loader | ml/cwru_loader.py | same (verbatim) | **VERIF/PARTIAL** (M1; data-dependent tests skip) | TEST_EVIDENCE §M1 |
| Domain core | DQ scenarios (three gates) | tests/integration/data_quality_scenarios.py | same (translate import cloud-free) | **VERIF** (M1) | TEST_EVIDENCE §M1 |
| Domain core | Settings model (lazy validation) | config/settings.py (Azure) | config/settings.py (Kinesis/S3, no boto3) | **IMPL→VERIF** (M1) | TEST_EVIDENCE §M1 |
| **Ingestion** | Streaming bus | Event Hubs | Kinesis Data Streams | **NYI** (M2) | — |
| Ingestion | Consumer receive→validate→buffer | eventhub_consumer.py | kinesis_consumer.py | **NYI** (M2) | — |
| Ingestion | Checkpoint store | FileCheckpointManager | file (dev) + DynamoDB lease (prod) | **NYI** (M2) | — |
| Ingestion | DLQ | ADLS _dlq/ | S3 _dlq/ | **NYI** (M2) | — |
| Ingestion | Producer / NATS bridge | edge/*.py | Kinesis producer + same translate | **NYI** (M2) | — |
| **Raw storage** | Landing JSONL, date-partitioned | ADLS raw/telemetry | S3 raw/telemetry | **NYI** (M3) | — |
| Raw storage | Versioning / lifecycle / encryption | ADLS + P0-05/P1-09 | S3 versioning + lifecycle + KMS | **NYI** (M3/M4) | — |
| **Processing** | Auto Loader Bronze | cloudFiles abfss | cloudFiles s3 | **NYI** (M7) | — |
| Processing | Silver clean+dedup+quarantine | dlt/silver/* | same (verbatim) | **SPEC** | — |
| Processing | Config-driven flatten | flatten_payloads.py | same (verbatim) | **SPEC** | — |
| Processing | Gold KPIs + evidence + ML features | dlt/gold/* | same (verbatim) | **SPEC** | — |
| **Governance** | Unity Catalog | Access Connector MI → abfss | IAM role → s3 external location | **NYI** (M6) | — |
| **ML/MLOps** | Train/eval/CloudForest + MLflow | ml/* jobs | same (S3 URIs) | **NYI** (M8) | — |
| **Security** | Identity | Managed Identity | IAM roles (least priv) | **NYI** (M4/M5) | — |
| Security | Secrets | Key Vault | Secrets Manager + KMS | **NYI** (M4/M5) | — |
| Security | Encryption | platform | KMS CMKs | **NYI** (M4/M5) | — |
| Security | CI auth | OIDC→Azure AD | OIDC→AWS IAM role | **NYI** (M9) | — |
| **Observability** | Logs/metrics/alarms | Azure Monitor/App Insights | CloudWatch + CloudTrail | **NYI** (M10) | — |
| **Networking** | Private connectivity | (implicit) | VPC + endpoints, block public | **NYI** (M4/M5) | — |
| **CI/CD** | Plan/apply + PR diff + smoke | ci.yml etc. | AWS OIDC workflows | **NYI** (M9) | — |
| **Infra** | Terraform modules + remote state | azurerm | AWS provider + S3/DynamoDB backend | **NYI** (M4) | — |
| **Reliability** | Failure/recovery | (Azure runbooks) | injected-failure tests | **NYI** (M11) | — |

## Rule

`IMPLEMENTED` never becomes `VERIFIED` without an executed test recorded in
`TEST_EVIDENCE.md`. `VERIFIED` never becomes `HARDENED` without production
controls + a failure test.
