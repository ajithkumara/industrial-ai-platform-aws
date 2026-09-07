# CROSS_CLOUD_PARITY.md — Milestone 16

> Azure `industrial-ai-platform` vs AWS `industrial-ai-platform-aws`. The goal
> is identical platform SEMANTICS, not identical infrastructure. Every row cites
> executed evidence or an explicit NOT EXECUTED with the reason.

| Capability | Azure service | AWS service | Logical contract | Behavioural equivalence | Evidence | Known difference |
|---|---|---|---|---|---|---|
| Telemetry envelope | Pydantic | Pydantic (identical) | 7-field generic envelope, extra=forbid, min_length=1 | EXACT (byte-identical) | E1 (9 tests) | none |
| Asset onboarding | config/asset_types + helpers | identical | new type = YAML only | EXACT | E1 (21) | none |
| Ingress bus | Event Hubs | Kinesis Data Streams | ordered, replayable stream | BEHAVIOURAL | E-M2-1 | partition→shard; offset→sequence# |
| Consumer | eventhub_consumer | kinesis_consumer | validate→buffer→durable write→checkpoint (P0-01) | EXACT logic | E-M2-1 (P0-01) | transport SDK only |
| Checkpoint | local file / EH blob | file (dev) / DynamoDB lease (prod) | checkpoint after durable write; restart-safe | BEHAVIOURAL | E-M2-1, failure-recovery | prod store differs |
| Raw landing | ADLS JSONL | S3 JSONL | date-partitioned, immutable, DLQ isolated | EXACT layout | E-M2-1 | abfss→s3 URI |
| Bronze Auto Loader | cloudFiles abfss | cloudFiles s3 | schema-inferred streaming ingest | BEHAVIOURAL | silver-evidence | bronze_path only |
| Silver clean+dedup | dlt notebook | identical notebook | expectations + dedup by event_id | EXACT (byte-identical) | silver-evidence (local Spark) | none (config only) |
| Config-driven flatten | dlt notebook | identical | per-asset flatten, null-fallback | EXACT | silver-evidence (DQ8/9/10) | none |
| Gold KPIs + evidence + ML features | dlt notebooks | identical | domain-agnostic + leakage-safe | EXACT | gold-evidence, feature_spec | none |
| Unity Catalog | Access Connector MI → abfss | IAM role → s3 external location | catalog industrial_ai + schemas + grants | BEHAVIOURAL | terraform-evidence | credential mechanism |
| ML train/eval/CloudForest | Databricks jobs | identical notebooks | leakage-safe, reproducible, frozen threshold | EXACT | ml-evidence (17 tests) | s3 paths in job params |
| MLflow registry | UC 3-part | identical | industrial_ai.ml.<model> | EXACT | ml-evidence (contract) | none |
| Model backup | ADLS | S3 (adapted) | daily Prod/Staging copy | BEHAVIOURAL | ml-evidence | abfss→s3 dest |
| Secrets | Key Vault | Secrets Manager + KMS | placeholders, no committed values | BEHAVIOURAL | security-evidence S9 | auth model |
| Identity | Managed Identity + RBAC | IAM roles (least-priv) | scoped runtime access | BEHAVIOURAL | security-evidence S2 | none semantically |
| Encryption | platform-managed | KMS CMKs + rotation | at-rest + in-transit | AWS improvement | security-evidence S3 | CMKs added |
| Observability | Azure Monitor/App Insights | CloudWatch + CloudTrail | lag/DLQ/failure alarms | BEHAVIOURAL | OBSERVABILITY.md | metric names |
| Networking | implicit | VPC + endpoints, block public | private data plane | AWS improvement | security-evidence S8 | net added |
| CI auth | OIDC→Azure AD | OIDC→AWS IAM role | short-lived, no static keys | BEHAVIOURAL | cicd-evidence | provider |
| IaC + state | azurerm | AWS provider + S3/DynamoDB | modular, remote state, least-priv | BEHAVIOURAL | terraform-evidence | provider |
| Resource grouping | Resource Groups | tags + account/region | — | N/A | — | no RG concept |

## Semantic parity summary

Every business/data contract (envelope, asset configs, DQ gates, dedup,
leakage-safe ML, reproducibility) is EXACT — proven by byte-identical code +
executed tests. All cloud differences are confined to the infrastructure
boundary (transport, storage, identity, IaC) and each is a documented
BEHAVIOURAL translation or an AWS-native improvement — never a downgrade or a
weakened test.
