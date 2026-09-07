# security-evidence.md — AWS Security Review (Milestone 3/4 baseline)

> THREAT → CONTROL → IMPLEMENTATION → TEST → EVIDENCE for every important
> control. Controls are as-coded in Terraform; live enforcement is verified
> once the environment is applied (NOT EXECUTED items noted).

| # | Threat | Control | Implementation | Test | Evidence |
|---|---|---|---|---|---|
| S1 | Long-lived static credentials leak | No static keys; workloads assume IAM roles; CI uses GitHub OIDC | `modules/iam` roles + `aws_iam_openid_connect_provider.github`; `providers.tf` uses ambient creds | secret scan; checkov | terraform-evidence E-M4-3 |
| S2 | Over-broad runtime permissions | Least-privilege consumer/producer roles scoped to specific ARNs + actions | `modules/iam` consumer (Kinesis read / S3 raw/* write / DynamoDB RW / KMS) ; producer (Kinesis write / KMS) | checkov IAM checks pass on runtime roles | E-M4-2 |
| S3 | Data at rest exposure | KMS CMK encryption everywhere (S3, Kinesis, DynamoDB, Secrets, CloudTrail, ECR, logs) with rotation + key policy | `modules/kms` + SSE configs in each module | checkov CKV_AWS_* encryption checks pass; CKV2_AWS_64 fixed | E-M4-2 |
| S4 | Data in transit interception | TLS-only S3 bucket policy (deny `aws:SecureTransport=false`); private VPC endpoints | `modules/s3` bucket policy; `modules/vpc` endpoints | checkov; policy present | E-M4-1/2 |
| S5 | Public data exposure | S3 Block Public Access (all 4) on every bucket | `aws_s3_bucket_public_access_block` on lake/logs/trail/state | checkov CKV_AWS public checks pass | E-M4-2 |
| S6 | Undetected control-plane actions | CloudTrail multi-region + log-file validation, KMS, locked sink | `modules/cloudtrail` | checkov; trail defined | E-M4-2 |
| S7 | Accidental data destruction | `prevent_destroy` on lake/state/trail/log buckets (Azure P0-02 parity) | lifecycle blocks | plan fails on destroy (NOT EXECUTED — needs apply) | terraform-evidence NOT EXECUTED |
| S8 | Network exfiltration / public egress | Private subnets only, gateway+interface endpoints, deny-all default SG, VPC flow logs | `modules/vpc` | checkov; flow log defined | E-M4-2 |
| S9 | Secret sprawl in repo | Secrets Manager placeholders (blank, `ignore_changes`); no values committed | `modules/secrets` | secret scan zero findings | E-M4-3 |
| S10 | Supply-chain (container) | ECR scan-on-push + immutable tags + KMS | `modules/ecr` | checkov; config present | E-M4-2 |
| S11 | Checkpoint tampering / loss | DynamoDB PITR + KMS; least-priv consumer access | `modules/dynamodb` + iam | checkov; moto restart-recovery test | ingestion-evidence E-M2-1 |

## Residual risks / accepted findings

- **R1 (top):** CI deploy role has broad `*` Terraform permissions
  (CKV_AWS_107/108/109/110/111/356). Necessary for IaC deploy; NOT
  AdministratorAccess. **Action B-M4-TIGHTEN (P1):** split into per-service
  scoped statements or use permission boundaries once the resource set is
  stable.
- **R2:** No S3 cross-region replication (CKV_AWS_144) — a prod DR decision,
  deferred with cost rationale.
- **R3:** Secrets auto-rotation not enabled (CKV2_AWS_57) — needs a rotation
  Lambda; deferred to a hardening milestone.
- **R4:** GitHub OIDC thumbprint is pinned to a known value — verify current
  GitHub thumbprint before apply.

## NOT EXECUTED (require AWS account)

Live enforcement of S5 (public-access block), S7 (prevent_destroy),
S6/S8 (trail + flow logs actually delivering) is verified after
`terraform apply` with: `aws s3api get-public-access-block`,
`aws cloudtrail get-trail-status`, attempting a guarded destroy. Commands are
in terraform-evidence.md. No enforcement result is fabricated.
