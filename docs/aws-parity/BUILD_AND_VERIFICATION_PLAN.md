# BUILD_AND_VERIFICATION_PLAN.md

> Governing workflow: **BUILD → TEST → VERIFY → DOCUMENT EVIDENCE → HARDEN → NEXT**.
> The AWS repo is specification-only today (Phase 0 docs). This plan sequences
> the implementation into dependency-ordered milestones, each with an
> acceptance gate that must pass before the next begins. Nothing is marked
> VERIFIED without an executed test; nothing is marked IMPLEMENTED because a
> doc says so.

## Reference authority

- **Azure `industrial-ai-platform`** = reference implementation for business/
  data contracts, logical pipeline behaviour, acceptance criteria, security
  intent, operational expectations.
- **`docs/reference/*` + `docs/aws/*`** (Phase 0) = the architectural
  specification and Azure→AWS mapping.
- **`ACCEPTANCE_CONTRACT.md`** = the logical results the AWS build must
  reproduce (never weakened to make tests pass).

## Milestone dependency graph

```
M1 Domain Core (cloud-free)  ── no deps
      |
      +--> M2 Ingestion (Kinesis consumer, S3 client, DynamoDB checkpoint)
      |         depends on: M1 (batch_buffer, envelope, settings)
      |
      +--> M3 Data Lake / S3 layout + lifecycle/encryption
      |         depends on: M2 (storage client contract)
      |
M4 Terraform (S3, Kinesis, DynamoDB, IAM, KMS, Secrets, VPC, CW, CT, ECR)
      depends on: M2/M3 resource contracts
      |
      +--> M5 Networking + Security review (threat model per control)
      |
      +--> M6 Databricks on AWS + Unity Catalog (workspace, storage cred, catalog)
      |         depends on: M4 (S3, IAM role for UC)
      |
      +--> M7 Data pipeline Bronze→Silver→Gold (DLT notebooks, S3 URIs)
      |         depends on: M6 (UC), M3 (S3 landing)
      |
      +--> M8 ML / MLOps (feature table, train/eval, CloudForest, MLflow)
      |         depends on: M7 (Gold feature source)
      |
M9 CI/CD (AWS OIDC, plan/apply, bundle validate, tests, scanning)
      depends on: M4 (infra), M1 (tests)
      |
M10 Observability (CloudWatch metrics/alarms, dashboards, runbooks)
      depends on: M2,M4,M7,M8
      |
M11 Failure/recovery testing (restart, DLQ replay, checkpoint loss, rollback)
      depends on: M2,M7
      |
M12 Full parity review (FORENSIC_REVIEW, TEST_EVIDENCE, SECURITY_REVIEW, ...)
      depends on: all above
      |
M13 Final production-readiness scoring
```

## Acceptance gates (per milestone)

| M | Gate (must pass before next) |
|---|---|
| M1 | pure-Python unit/contract/schema/DQ tests pass; deterministic fixtures reproduce expected values; no AWS SDK coupling in domain logic; static analysis clean |
| M2 | happy-path + malformed + duplicate + restart + checkpoint recovery + transient failure + DLQ + replay + backpressure tests pass (moto) |
| M3 | S3 read/write/idempotency/partitioning tests pass; encryption + block-public verified in plan |
| M4 | `terraform fmt -check`, `validate`, `plan` clean; IaC scan (tfsec/checkov) no criticals; least-privilege review |
| M5 | threat model per control (THREAT→CONTROL→IMPL→TEST→EVIDENCE); no public data paths |
| M6 | UC catalog/schemas/grants provisioned; storage credential to S3 verified |
| M7 | end-to-end Bronze→Silver→Gold reproduces ACCEPTANCE_CONTRACT logical results |
| M8 | recording-level split isolation, TRAIN normal-only, zero feature NULLs, deterministic seed/threshold reproduced |
| M9 | pipeline blocks deploy on failed acceptance tests |
| M10 | every critical component: HEALTH→METRIC→ALARM→LOG→RUNBOOK |
| M11 | system recovers predictably from each injected failure |
| M12 | every parity claim has executed evidence |
| M13 | RED/AMBER/GREEN per domain, no inflation |

## First milestone (this iteration)

**M1 — Repository + Domain Core.** Cloud-free foundation: envelope, config
model, asset-type configs + loader, ML spec/scoring/loader, batch buffer,
shared utils, and every pure-Python contract/schema/DQ test, executed for
real. Then update `PARITY_MATRIX.md` from IMPLEMENTED→VERIFIED only for tests
that actually ran, write `TEST_EVIDENCE.md`, and stop.
