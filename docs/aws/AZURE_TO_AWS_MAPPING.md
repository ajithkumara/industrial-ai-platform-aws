# AZURE_TO_AWS_MAPPING.md

> Phase 0K deliverable. Each CURRENT component mapped to its AWS-native
> equivalent **by architectural responsibility**, not by forced 1:1. Cloud
> agnosticism is deliberately abandoned — AWS services are used directly.

## Service-level mapping

| Responsibility | Azure (current) | AWS (target) | Notes |
|---|---|---|---|
| Event ingress / streaming bus | Azure Event Hubs (namespace, hub `telemetryhub`, 2 partitions, CG `bronze-loader`, 7-day retention) | **Amazon Kinesis Data Streams** (2 shards, 168h retention, dedicated consumer / enhanced fan-out) | Partition→shard; offset→sequence number |
| Consumer offset/checkpoint | Local JSON (dev) | Local JSON (dev) + **DynamoDB lease table** (prod, KCL-native) | Do not ship local file checkpoint to prod |
| Raw/landing + medallion storage | ADLS Gen2 (HNS, `datalake`+`checkpoint` filesystems) | **Amazon S3** (bucket + `raw/`, `checkpoint/` prefixes; versioning; lifecycle; KMS SSE; block public access) | JSONL layout + date partitioning identical |
| Dead letter queue | ADLS `raw/telemetry/_dlq/` | **S3** `raw/telemetry/_dlq/` | Same structure |
| Lakehouse compute | Azure Databricks (premium) | **Databricks on AWS** (premium) | Bundle/DLT/jobs portable |
| Governance / catalog | Unity Catalog (Access Connector MI → external location abfss) | **Unity Catalog on AWS** (IAM role / UC storage credential → external location `s3://`) | Catalog `industrial_ai`, schemas identical |
| Secrets | Azure Key Vault | **AWS Secrets Manager** (+ KMS) | EH/storage conn strings → Kinesis/S3 config secrets |
| Identity / access | Managed Identity + Azure RBAC role assignments | **AWS IAM** roles + policies (least privilege) | Access Connector → instance profile / UC credential role |
| Encryption keys | (platform-managed) | **AWS KMS** (CMKs for S3, Secrets, Kinesis) | AWS-specific improvement |
| Monitoring / logs | Log Analytics + App Insights + diagnostic settings | **CloudWatch** (log groups, metrics, alarms, dashboards) | Diagnostic settings → CloudWatch/metric filters |
| Audit trail | Azure Activity Log / KV audit | **AWS CloudTrail** | AWS-native improvement |
| Networking | (implicit / public endpoints) | **Amazon VPC** (private subnets, endpoints, no public S3/data) | Phase 9 |
| Container registry | (n/a) | **Amazon ECR** (consumer image + scanning) | Phase 11 |
| MLflow / model registry | Databricks MLflow + UC `industrial_ai.ml.*` | **Databricks MLflow on AWS + UC** | Identical three-part names |
| CI auth | GitHub OIDC → Azure AD federated credential | **GitHub OIDC → AWS IAM role** (`configure-aws-credentials`) | No static keys either cloud |
| TF state backend | azurerm (blob) | **S3 backend + DynamoDB lock** | — |
| Resource grouping | Resource Groups | Tags + account/region conventions | AWS has no RG; not 1:1 |

## Component file mapping (repo-level)

| Current file | AWS file | Action |
|---|---|---|
| `shared/telemetry_event.py` | same | verbatim |
| `config/asset_types/*.yml` | same | verbatim |
| `dlt/common/helpers.py`, all `dlt/**` | same | verbatim (bronze_path→s3 in pipeline config only) |
| `ml/feature_spec.py`, `ml/bearing_model_common.py`, `ml/cwru_loader.py` | same | verbatim |
| `consumer/batch_buffer.py` | same | verbatim |
| `consumer/eventhub_consumer.py` | `consumer/kinesis_consumer.py` | adapt (KCL/boto3; same ordering + DLQ) |
| `consumer/checkpoint.py` | `consumer/checkpoint.py` (+ `dynamo_checkpoint.py`) | adapt for prod |
| `consumer/storage_client.py` | `consumer/storage_client.py` (S3/boto3) | adapt (same JSONL + DLQ layout) |
| `edge/base_producer.py` | `edge/base_producer.py` (Kinesis PutRecords) | adapt |
| `edge/vehicle_producer.py`, `edge/nats_bearing_bridge.py` | same (translate logic) + Kinesis producer | translate logic verbatim; producer adapted |
| `config/settings.py`, `config/environments/*` | same names | adapt (Kinesis/S3 fields) |
| `terraform/**` | `terraform/**` (AWS provider, new modules) | full AWS-native translation |
| `.github/workflows/*` | same names | adapt auth to AWS OIDC |
| `monitoring/alert_rules.json` | CloudWatch alarms (TF) | translate |

## Responsibility-based cautions (NOT 1:1)

- **Resource Groups have no AWS equivalent** — do not invent one; use tags.
- **Event Hubs consumer groups ≠ Kinesis** — Kinesis uses dedicated
  consumers / enhanced fan-out + a KCL app name; the "bronze-loader" concept
  becomes a KCL application name + DynamoDB lease table.
- **Managed Identity → IAM role**, but Databricks-on-AWS S3 access is via a
  UC storage credential backed by an IAM role the workspace assumes — not a
  per-resource identity.
- **Key Vault access policies → IAM + Secrets Manager resource policies** —
  the auth model differs; preserve least privilege, not the mechanism.
