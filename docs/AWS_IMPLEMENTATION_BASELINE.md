# AWS_IMPLEMENTATION_BASELINE.md

> Forensic baseline for `industrial-ai-platform-aws` vs the Azure reference
> `industrial-ai-platform`. Reflects the **actual current state** (evidence,
> not aspiration): Milestone 1 (domain core) is IMPLEMENTED + VERIFIED;
> everything downstream is MISSING pending its milestone. Detailed component
> analysis lives in `docs/reference/*` (Phase 0) and `docs/aws-parity/*`
> (build plan, parity matrix, acceptance contract, test evidence). This file
> is the single-page classification index the mega-spec Phase 0 requires.

## Classification legend
`EXACT` exact parity (identical code/behaviour) · `BEHAVIOURAL` same logical
contract, AWS-native mechanism · `AWS-SPECIFIC` new AWS implementation ·
`N/A` no AWS equivalent needed · `MISSING` not yet implemented.

## Repository architecture

- **Azure ref**: Event Hubs → Python consumer → ADLS Gen2 (JSONL) → Databricks
  Auto Loader → DLT Bronze/Silver/Gold → ML jobs (MLflow/UC). IaC: Terraform
  (azurerm). CI: GitHub Actions OIDC→Azure AD.
- **AWS target**: Kinesis Data Streams → Python consumer → S3 (JSONL) →
  Databricks-on-AWS Auto Loader → same DLT notebooks → same ML jobs. IaC:
  Terraform (aws). CI: GitHub Actions OIDC→AWS IAM role.
- **AWS current**: domain core only (envelope, asset configs, DLT notebooks
  copied, ML spec/scoring/loader, batch buffer, settings). Verified by 129
  passing tests. No transport, storage client, infra, or pipeline runtime yet.

## Component classification (current)

| Component | Azure | AWS mechanism | Class | State | Evidence |
|---|---|---|---|---|---|
| Telemetry envelope | shared/telemetry_event.py | identical | EXACT | VERIFIED | TEST_EVIDENCE E1 |
| Asset-type configs + loader | config/asset_types + dlt/common/helpers | identical | EXACT | VERIFIED | E1 |
| Batch buffer + P0-01 ordering | consumer/batch_buffer.py | identical (TYPE_CHECKING guard) | EXACT | VERIFIED | E1 |
| ML feature spec / scoring / loader | ml/*.py | identical | EXACT | VERIFIED | E1 |
| DQ three-gate contract | data_quality_scenarios | identical | EXACT | VERIFIED | E1 |
| NATS translate logic | edge/nats_bearing_bridge translate_* | identical (lazy producer) | EXACT | VERIFIED | E1 |
| Settings model | config/settings.py | Kinesis/S3/DynamoDB dataclasses | BEHAVIOURAL | VERIFIED | E1 |
| DLT Bronze/Silver/Gold notebooks | dlt/** | identical (S3 bronze_path) | BEHAVIOURAL | copied, not yet run | — |
| Streaming ingress | Event Hubs | Kinesis Data Streams | BEHAVIOURAL | MISSING (M2) | — |
| Consumer runtime | eventhub_consumer.py | kinesis_consumer.py | BEHAVIOURAL | MISSING (M2) | — |
| Raw storage client | ADLS DataLakeServiceClient | S3 boto3 | BEHAVIOURAL | MISSING (M2) | — |
| Checkpoint store | local JSON file | file (dev) + DynamoDB lease (prod) | BEHAVIOURAL/AWS-SPECIFIC | MISSING (M2) | — |
| DLQ | ADLS _dlq/ | S3 _dlq/ | BEHAVIOURAL | MISSING (M2) | — |
| Producer / simulator | edge/base_producer (EH) | edge/base_producer (Kinesis) | BEHAVIOURAL | MISSING (M2) | — |
| Unity Catalog governance | Access Connector MI → abfss | IAM role → s3 external location | BEHAVIOURAL | MISSING (M6) | — |
| ML training/eval/CloudForest | ml jobs (Databricks) | same (S3 URIs) | BEHAVIOURAL | MISSING (M8) | — |
| Secrets | Key Vault | Secrets Manager + KMS | BEHAVIOURAL | MISSING (M4) | — |
| Identity | Managed Identity + RBAC | IAM roles (least priv) | BEHAVIOURAL | MISSING (M4/M5) | — |
| Encryption | platform-managed | KMS CMKs | AWS-SPECIFIC | MISSING (M4) | — |
| Networking | (implicit) | VPC + endpoints, block public | AWS-SPECIFIC | MISSING (M4/M5) | — |
| Audit | Activity log / KV audit | CloudTrail | AWS-SPECIFIC | MISSING (M4) | — |
| Container registry | (n/a) | ECR + scan | AWS-SPECIFIC | MISSING (M4/M9) | — |
| Observability | Azure Monitor / App Insights | CloudWatch + CloudTrail | BEHAVIOURAL | MISSING (M10) | — |
| CI auth | OIDC→Azure AD | OIDC→AWS IAM role | BEHAVIOURAL | MISSING (M9) | — |
| TF remote state | azurerm backend | S3 + DynamoDB lock | BEHAVIOURAL | MISSING (M4) | — |
| Resource Groups | RG per env | tags + account/region | N/A | N/A | — |

## Difference summary (by concern)

- **Configuration**: env-var names change (KINESIS_*/S3_*/AWS_REGION vs
  EVENTHUB_*/STORAGE_*); frozen-dataclass shape + lazy-validation contract
  identical.
- **Authentication**: Managed Identity → IAM roles; CI OIDC→Azure AD →
  OIDC→AWS IAM role. No static credentials either cloud.
- **Storage**: ADLS Gen2 HNS filesystems → S3 buckets/prefixes; same JSONL
  layout, date partitioning, DLQ prefix.
- **Streaming**: EH partitions/consumer-group/offset → Kinesis
  shards/KCL-app/sequence-number. Ordering guaranteed per shard (as per
  partition on EH).
- **Checkpoint/state**: local JSON (dev, both) → DynamoDB lease (AWS prod)
  vs EH blob checkpoint store (Azure prod). Same "checkpoint only after
  durable write" P0-01 invariant.
- **Databricks/UC**: workspace + UC identical concepts; storage credential
  backed by IAM role (S3) vs Access Connector MI (abfss).
- **Observability**: CloudWatch/CloudTrail vs Log Analytics/App Insights.
- **CI/CD & IaC**: GitHub Actions + Terraform on both; provider + auth swap.

## Honest boundary

Per agreement, live-cloud steps (terraform apply, deployed-resource
verification, live CI runs) require the user's AWS account and are **not**
executed by this build; they are delivered deploy-ready with exact commands
and marked NOT EXECUTED in `docs/evidence/*`. No cloud resource, URL, or
deployment result is fabricated.
