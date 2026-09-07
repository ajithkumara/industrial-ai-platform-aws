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
| **Ingestion** | Streaming bus | Event Hubs | Kinesis Data Streams | **VERIFIED** (M2, moto) | ingestion-evidence E-M2-1 |
| Ingestion | Consumer receive→validate→buffer | eventhub_consumer.py | kinesis_consumer.py | **VERIFIED** (M2) | E-M2-1 (P0-01) |
| Ingestion | Checkpoint store | FileCheckpointManager | file (dev) + DynamoDB lease (prod) | **VERIFIED** (M2, moto) | E-M2-1 (restart recovery) |
| Ingestion | DLQ | ADLS _dlq/ | S3 _dlq/ | **VERIFIED** (M2, moto) | E-M2-1 |
| Ingestion | Producer / NATS bridge | edge/*.py | Kinesis producer + same translate | **VERIFIED** (M2) | E-M2-1 + M1 translate |
| **Raw storage** | Landing JSONL, date-partitioned | ADLS raw/telemetry | S3 raw/telemetry | **VERIFIED** (M2, moto) | E-M2-1 |
| Raw storage | Versioning / lifecycle / encryption | ADLS + P0-05/P1-09 | S3 versioning + lifecycle + KMS | **IMPLEMENTED** (hcl2+checkov; apply NOT EXECUTED) | terraform-evidence E-M4 |
| **Processing** | Auto Loader Bronze | cloudFiles abfss | cloudFiles s3 (bundle bronze_path) | **IMPLEMENTED** (bundle; live run NOT EXECUTED) | silver-evidence |
| Processing | Silver clean+dedup+quarantine | dlt/silver/* | identical (verbatim) | **VERIFIED** (local Spark; DLT run NOT EXECUTED) | silver-evidence |
| Processing | Config-driven flatten | flatten_payloads.py | identical (verbatim) | **VERIFIED** (local Spark DQ8/9/10) | silver-evidence |
| Processing | Gold KPIs + evidence + ML features | dlt/gold/* | identical (verbatim) | **VERIFIED** (local Spark + feature_spec) | gold-evidence |
| **Governance** | Unity Catalog | Access Connector MI → abfss | IAM role → s3 external location | **IMPLEMENTED** (hcl2+checkov; apply NOT EXECUTED) | terraform-evidence |
| **ML/MLOps** | Train/eval/CloudForest + MLflow | ml/* jobs | identical (S3 URIs) | **VERIFIED** (contract+repro; live run NOT EXECUTED) | ml-evidence |
| **Security** | Identity | Managed Identity | IAM roles (least priv) | **IMPLEMENTED** (checkov; runtime roles least-priv) | security-evidence S2 |
| Security | Secrets | Key Vault | Secrets Manager + KMS | **IMPLEMENTED** (blank placeholders) | security-evidence S9 |
| Security | Encryption | platform | KMS CMKs | **IMPLEMENTED** (CMK+rotation+policy) | security-evidence S3 |
| Security | CI auth | OIDC→Azure AD | OIDC→AWS IAM role | **IMPLEMENTED** (workflows; live runs NOT EXECUTED) | cicd-evidence |
| **Observability** | Logs/metrics/alarms | Azure Monitor/App Insights | CloudWatch + CloudTrail | **IMPLEMENTED** (alarms coded; live metrics NOT EXECUTED) | terraform-evidence E-M4 |
| **Networking** | Private connectivity | (implicit) | VPC + endpoints, block public | **IMPLEMENTED** (checkov) | security-evidence S8 |
| **CI/CD** | Plan/apply + PR diff + smoke | ci.yml etc. | AWS OIDC workflows | **IMPLEMENTED** (YAML valid; live runs NOT EXECUTED) | cicd-evidence |
| **Infra** | Terraform modules + remote state | azurerm | AWS provider + S3/DynamoDB backend | **IMPLEMENTED** (39 .tf, hcl2+checkov 244 pass; plan/apply NOT EXECUTED) | terraform-evidence E-M4 |
| **Reliability** | Failure/recovery | (Azure runbooks) | injected-failure tests | **VERIFIED** (5 moto failure tests) | AWS_FAILURE_ENGINEERING |

## Rule

`IMPLEMENTED` never becomes `VERIFIED` without an executed test recorded in
`TEST_EVIDENCE.md`. `VERIFIED` never becomes `HARDENED` without production
controls + a failure test.
