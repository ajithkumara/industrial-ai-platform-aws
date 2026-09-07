# HARDENING_BACKLOG.md

> Live backlog for the AWS build. Milestone-scoped. IDs are stable. This is
> not a one-shot "everything missing" dump — it is the execution backlog that
> grows/updates as each milestone lands and its review surfaces real findings.
> Priorities: **P0** blocking correctness/security/reproducibility · **P1**
> production-readiness · **P2** hardening · **P3** enhancement.

## Build backlog (milestone → work items)

| ID | Pri | Area | Item | Acceptance | Milestone |
|---|---|---|---|---|---|
| B-M1-01 | P0 | Domain | Scaffold repo; copy verbatim cloud-free core | pytest collects; imports clean | M1 |
| B-M1-02 | P0 | Domain | AWS-shaped settings (Kinesis/S3), lazy validation, no boto3 in domain | test_settings_module passes | M1 |
| B-M1-03 | P0 | Domain | Port all pure-Python contract/schema/DQ/ML tests unweakened | tests execute & pass | M1 |
| B-M2-01 | P0 | Ingestion | Kinesis consumer (receive→validate→buffer→S3→checkpoint) | happy-path moto test | M2 |
| B-M2-02 | P0 | Ingestion | S3 storage client (JSONL + DLQ, date-partitioned) | moto read/write test | M2 |
| B-M2-03 | P0 | Ingestion | Checkpoint: file (dev) + DynamoDB lease (prod) | checkpoint recovery test | M2 |
| B-M2-04 | P0 | Ingestion | Preserve P0-01 ordering (checkpoint after durable write) | test_batch_buffer + consumer test | M2 |
| B-M2-05 | P1 | Ingestion | Kinesis producer + NATS bridge (translate verbatim) | test_nats_bearing_bridge | M2 |
| B-M2-06 | P1 | Ingestion | Duplicate/malformed/backpressure/graceful-shutdown | failure tests | M2/M11 |
| B-M3-01 | P0 | Storage | S3 bucket layout, deterministic paths, idempotent writes | moto test | M3 |
| B-M3-02 | P1 | Storage | Versioning + lifecycle (IA/Glacier) + KMS SSE + block public | terraform plan assertions | M3/M4 |
| B-M4-01 | P0 | Infra | Terraform modules: s3, kinesis, dynamodb, iam, kms, secrets, vpc, cloudwatch, cloudtrail, ecr | fmt/validate/plan clean | M4 |
| B-M4-02 | P0 | Infra | Remote state: S3 backend + DynamoDB lock | init succeeds | M4 |
| B-M4-03 | P0 | Security | No static creds; secrets blank-with-comment; least-priv IAM | IaC scan no criticals | M4/M5 |
| B-M5-01 | P1 | Security | Threat model per control (THREAT→CONTROL→IMPL→TEST→EVIDENCE) | SECURITY_REVIEW.md | M5 |
| B-M6-01 | P0 | Databricks | Workspace + UC storage credential (IAM role → S3), catalog/schemas/grants | UC objects present | M6 |
| B-M7-01 | P0 | Pipeline | DLT Bronze→Silver→Gold on S3 (notebooks verbatim, bronze_path=s3) | e2e reproduces ACCEPTANCE_CONTRACT | M7 |
| B-M8-01 | P0 | ML | Feature table + train/eval + CloudForest on AWS + MLflow | ML invariants reproduced | M8 |
| B-M9-01 | P0 | CI/CD | AWS OIDC workflows; deploy blocked on failed acceptance | pipeline run | M9 |
| B-M10-01 | P1 | Observability | CloudWatch metrics/alarms/dashboards + runbooks | HEALTH→METRIC→ALARM→LOG→RUNBOOK | M10 |
| B-M11-01 | P1 | Reliability | Injected-failure suite (restart, DLQ replay, checkpoint loss, rollback) | recovery verified | M11 |

## Findings backlog (populated by milestone reviews)

| B-M4-TIGHTEN | P1 | Security | CI deploy IAM role uses broad `*` Terraform perms (checkov CKV_AWS_107-111/356) | Split into per-service scoped statements or permission boundary once resource set stable | security-evidence R1 |
| F-M1-01 | P3 | Lint | Two unused symbols inherited verbatim from Azure ref (`defaultdict` in batch_buffer, `splits` in cwru_loader) | Remove in a lint-cleanup pass; no behavioural impact | M1 evidence E3 |

## Execution order (dependency-respecting)

M1 → M2 → M3 → M4 → M5 → M6 → M7 → M8 → M9 → M10 → M11 → M12 → M13.
Within a milestone, P0 before P1 before P2. A failed gate blocks the next
milestone until fixed or an exception is documented.
