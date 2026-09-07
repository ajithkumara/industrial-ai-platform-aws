# TERRAFORM_COMPONENT_MAPPING.md — Current Azure Platform

> Phase 0H deliverable. What each Terraform module actually creates, its
> variables/outputs/dependencies, and state/backend model.

## Layout

- `terraform/bootstrap/` — one-time backend bootstrap (creates the TF state
  storage account/container `sttfstate*` / `terraformstate`). Has its own
  local state (`terraform.tfstate` committed for bootstrap only).
- `terraform/environments/{dev,test,prod}/` — per-env root modules. Each has
  `main.tf`, `variables.tf`, `outputs.tf`, `providers.tf`, `versions.tf`,
  `backend.tf` + `backend.hcl` (azurerm remote state), `terraform.tfvars`.
- `terraform/modules/` — reusable modules (below).
- `terraform/unity_catalog/dev/` + `terraform/modules/unity_catalog/` — a
  standalone UC composition (catalog/external_location/storage_credential/
  schema/grants) usable independently of the databricks module.

## Modules and what they create

| Module | Creates | Key vars | Key outputs |
|---|---|---|---|
| `resource_group` | `azurerm_resource_group` | project, env, location, tags | name, location |
| `storage` | ADLS Gen2 account (HNS on), `datalake` + `checkpoint` filesystems; **blob versioning [P0-05]**, **lifecycle policy [P1-09]** (cool/archive), **prevent_destroy [P0-02]** | storage_account_name, rg, location | id, name, primary_connection_string, datalake_container_name |
| `eventhub` | namespace (Standard, cap 1), hub `telemetryhub` (2 partitions, **7-day retention [P1-14]**), consumer group `bronze-loader`, send/listen auth rules | name_suffix, rg | namespace_id, namespace_name, eventhub_name, producer/consumer connection strings |
| `access_connector` | `azurerm_databricks_access_connector` (SystemAssigned identity) | name_suffix | id, principal_id |
| `rbac` | role assignment (Storage Blob Data Contributor) for the connector on storage; **CI SP User Access Administrator [scoped]** | scope, principal_id, ci_principal_object_id | principal_id |
| `keyvault` | Key Vault (**prevent_destroy [P0-02]**) storing EH producer/consumer + storage connection strings; access policy for Databricks MI | name_suffix, mi_object_id, connection strings | key_vault_id |
| `databricks` | `azurerm_databricks_workspace` (premium) + UC: storage credential, external location `industrial_ai_lake`, catalog `industrial_ai`, schemas bronze/silver/gold/serving/ml, least-priv grants | rg, location, name_suffix, storage_account_name, container, access_connector id/principal, principal | workspace_url, workspace_id, workspace_resource_id, catalog_name, storage_credential_name, external_location_name |
| `monitoring` | Log Analytics workspace, App Insights, **diagnostic settings [P0-03]** (storage/KV/EH/Databricks), action group, **alerts**: DLT failure, EH lag, **consumer-group lag [P1-13]**, **ADLS write-failure [P1-13]**, **cost budget** | rg, location, name_suffix, eventhub_namespace_id, subscription_id, storage_account_id, key_vault_id, databricks_workspace_resource_id | log_analytics_workspace_id, app_insights_* |
| `unity_catalog` (standalone) | catalog/external_location/storage_credential/schema/grants as separate composition | — | — |

## Environment root wiring (dev, mirrored in test/prod after P1-06/07)

`data.azurerm_subscription.current` → storage_account_name override logic →
resource_group → storage → eventhub → access_connector → rbac (with
ci_principal_object_id) → keyvault → databricks (depends_on rbac) →
monitoring (passed storage/kv/databricks ids + subscription id).

## Auth / state

- **GitHub OIDC [P1-08]**: `use_oidc = true` in azurerm provider; no
  `ARM_CLIENT_SECRET`. `ARM_CLIENT_ID/TENANT_ID/SUBSCRIPTION_ID` are GitHub
  repo *variables*. Requires federated identity credentials on the App
  Registration (`pull_request` + `environment:dev` subjects).
- Remote state: azurerm backend (`backend.hcl` per env).

## AWS impact — module-by-module translation

| Azure module | AWS module | Notes |
|---|---|---|
| resource_group | (none — use tags + account/region) | AWS has no resource groups; use consistent tags + naming |
| storage | `s3` (bucket, versioning, lifecycle cool→IA/Glacier, `prevent_destroy`, KMS SSE, block public access) | ADLS `datalake`/`checkpoint` → S3 prefixes or separate buckets |
| eventhub | `kinesis` (data stream, retention 168h, consumer/enhanced-fanout) | 2 partitions → shards; auth rules → IAM policies |
| access_connector | `iam` (instance profile / UC storage credential role for S3) | Managed identity → IAM role assumed by Databricks |
| rbac | `iam` policies/role-attachments | scoped least-privilege S3 access |
| keyvault | `secrets_manager` (+ KMS) | connection strings → secrets |
| databricks | `databricks` (workspace on AWS + UC storage credential for S3, external location `s3://`, same catalog/schemas/grants) | premium workspace; UC identical |
| monitoring | `cloudwatch` (log groups, metric alarms, dashboards) + CloudTrail | diagnostic settings → CloudWatch/metric filters |
| — | `vpc`, `kms`, `ecr`, `cloudtrail` (new AWS-native) | private networking, encryption, image registry, audit |

Backend: azurerm → S3 backend + DynamoDB state lock. Auth: Azure OIDC →
**AWS OIDC → IAM role** (`role-to-assume`, no static keys). See
`docs/aws/AZURE_TO_AWS_MAPPING.md`. Classification: **AZURE-SPECIFIC —
full AWS-native translation required.**
