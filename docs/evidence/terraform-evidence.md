# terraform-evidence.md — Milestone 3/4 (AWS Infrastructure)

- **Date (UTC):** 2026-09-07
- **Scope:** terraform/bootstrap + 10 modules (kms, s3, kinesis, dynamodb, iam,
  secrets, ecr, vpc, cloudwatch, cloudtrail) + environments/dev.

## What was implemented

| Module | Resources | Azure parity |
|---|---|---|
| bootstrap | S3 state bucket (versioned, KMS, block-public, prevent_destroy) + DynamoDB lock | azurerm backend |
| kms | 6 CMKs (rotation + explicit key policy), aliases | platform-managed → CMKs |
| s3 | lake bucket + logs bucket: versioning, KMS SSE, lifecycle IA/Glacier, abort-multipart, TLS-only policy, block-public, prevent_destroy, access logging | ADLS + P0-02/P0-05/P1-09 |
| kinesis | data stream, 168h retention, KMS | Event Hubs + P1-14 |
| dynamodb | checkpoint lease table, PITR, KMS CMK | EH blob checkpoint |
| iam | consumer/producer least-priv roles + GitHub OIDC provider + CI role | Managed Identity + RBAC + P1-08 OIDC |
| secrets | Secrets Manager placeholders (blank, ignore_changes) | Key Vault |
| ecr | repo: scan-on-push, immutable tags, KMS, lifecycle | (new AWS) |
| vpc | private subnets, S3/DynamoDB gateway + Kinesis interface endpoints, deny-all default SG, flow logs | (new AWS) |
| cloudtrail | multi-region trail, log-file validation, KMS, locked S3 sink | Activity Log |
| cloudwatch | consumer log group, SNS alarm topic, 3 alarms (consumer lag, no-incoming, DLQ) | Azure Monitor + P1-13 |

## E-M4-1 — HCL syntax validation (python-hcl2)

Command: `python3 -c "import hcl2; [hcl2.load(open(f)) for f in glob('terraform/**/*.tf')]"`
Result: **39 .tf files parsed, 0 syntax errors.**

## E-M4-2 — IaC security scan (checkov 3.3.16)

Command: `checkov -d terraform --framework terraform`
Result: **244 passed, 27 failed** (after hardening pass; was 227/33).
Fixed in this milestone: KMS key policies (CKV2_AWS_64 x6), CloudWatch log
retention ≥1yr (CKV_AWS_338 x2), S3 abort-incomplete-multipart (CKV_AWS_300).

Accepted / deferred findings (documented, NOT silently ignored — see
`security-evidence.md` for full rationale):

| Check | Count | Disposition |
|---|---|---|
| CKV_AWS_107/108/109/110/111/356 (IAM `*`) | 9 | ACCEPTED — the **CI deploy role** legitimately needs broad Terraform perms (not AdministratorAccess). Runtime consumer/producer roles ARE least-privilege (scoped ARNs) and pass. Top hardening item B-M4-TIGHTEN. |
| CKV_AWS_144 (S3 cross-region replication) | 4 | DEFERRED — prod DR decision; not required at dev. |
| CKV2_AWS_62 (S3 event notifications) | 4 | DEFERRED — wired in M6/M7 (Auto Loader / SNS-SQS). |
| CKV2_AWS_61 (lifecycle on aux buckets) | 3 | ACCEPTED — logs/trail/state buckets; expiry policy is a later cost item. |
| CKV2_AWS_57 (Secrets rotation) | 2 | DEFERRED — needs a rotation Lambda per secret type. |
| CKV_AWS_18 (access logging on log/trail buckets) | 2 | ACCEPTED — a log bucket logging to itself is circular; trail bucket is an audit sink. |
| CKV_AWS_119 (DynamoDB CMK on lock table) | 1 | ACCEPTED — bootstrap lock table predates the KMS module (chicken-egg); uses AWS-managed key. |
| CKV_AWS_252 / CKV2_AWS_10 (CloudTrail SNS / CW Logs) | 2 | DEFERRED — trail→S3 is the primary durable sink; CW integration is additive. |

## E-M4-3 — Secret scan (Phase 9)

Commands: grep for `AKIA/ASIA`, `aws_secret_access_key`, `aws_session_token`,
`BEGIN PRIVATE KEY`, hardcoded password/token/client_secret, 12-digit account IDs.
Result: **zero findings** — only placeholders (`REPLACE_*`), descriptions, and
`data.aws_caller_identity`. No static credentials, no account IDs, no personal
paths anywhere.

## NOT EXECUTED (require your AWS account)

| Step | Command | Why |
|---|---|---|
| Format check | `terraform fmt -check -recursive` | terraform binary network-blocked in build env |
| Provider-schema validate | `terraform init -backend=false && terraform validate` | needs provider download |
| Plan | `terraform plan -var-file=terraform.tfvars` | needs AWS creds + state backend |
| Apply / deployed-resource verification | `terraform apply` then `aws s3 ls`, `aws kinesis describe-stream`, ... | needs AWS account |

hcl2 confirms syntax; checkov confirms security posture. Provider-schema
validate + plan/apply are yours to run — exact commands above. No resource,
ARN, or apply result is fabricated.

## Reproducibility (Phase 10)

A fresh AWS account reproduces the environment with:
```
cd terraform/bootstrap && terraform init && terraform apply -var account_suffix=<uniq>
cd ../environments/dev
cp backend.hcl.example backend.hcl   # fill from bootstrap outputs
cp terraform.tfvars.example terraform.tfvars   # fill unique suffixes
terraform init -backend-config=backend.hcl
terraform plan && terraform apply
```
No Azure subscription IDs, workspace IDs, URLs, account IDs, or personal
workstation paths appear anywhere in terraform/ (verified E-M4-3).
