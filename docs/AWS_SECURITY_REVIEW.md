# AWS_SECURITY_REVIEW.md — Milestone 5 (consolidated)

> Consolidated security review. Control detail + threat model is in
> `docs/evidence/security-evidence.md`; this is the executive summary + audit
> results. Scans were actually executed.

## Executed audit results

| Check | Command | Result |
|---|---|---|
| IaC security scan | `checkov -d terraform` | 274 passed / 27 failed (accepted set documented) |
| Secret scan | grep AKIA/ASIA, aws_secret_access_key, session_token, private keys, passwords, 12-digit account IDs | **zero findings** (only placeholders) |
| Static creds in CI | grep AWS_ACCESS_KEY_ID/SECRET in workflows | **zero** (OIDC only) |
| Dependency scan | `pip-audit -r requirements.txt` | no known vulnerabilities |

## Controls in place (as coded)

- **No static credentials**: workloads assume IAM roles; CI uses GitHub OIDC →
  IAM role (`id-token: write`); Databricks OAuth SP. No keys committed.
- **Least privilege (runtime)**: consumer role scoped to specific Kinesis/S3
  `raw/*`/DynamoDB/KMS ARNs; producer role to Kinesis write only.
- **Encryption**: KMS CMKs (rotation + key policy) on S3, Kinesis, DynamoDB,
  Secrets, CloudTrail, ECR, logs; TLS-only S3 bucket policy.
- **Public access**: S3 Block Public Access on every bucket.
- **Network**: private subnets, S3/DynamoDB/Kinesis VPC endpoints, deny-all
  default SG, VPC flow logs.
- **Audit**: CloudTrail multi-region + log-file validation + KMS.
- **Data protection**: S3 versioning + `prevent_destroy` on lake/state/trail
  buckets (Azure P0-02/P0-05 parity).
- **Supply chain**: ECR scan-on-push, immutable tags.

## Top residual risk

**R1 (P1) — CI deploy role breadth.** The GitHub-OIDC CI role uses broad `*`
Terraform permissions (checkov CKV_AWS_107-111/356) — necessary for IaC deploy,
not AdministratorAccess. Runtime roles are least-privilege. Action B-M4-TIGHTEN:
per-service scoping / permission boundary once the resource set stabilises.

Other accepted/deferred: S3 cross-region replication (prod DR), Secrets
auto-rotation (needs rotation Lambda), aux-bucket lifecycle — see
security-evidence.md residual risks.

## NOT EXECUTED

Live enforcement (public-access block, prevent_destroy guard, CloudTrail/flow
delivery) is verified after `terraform apply` — commands in terraform-evidence.md.
No enforcement result is fabricated.
