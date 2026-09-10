# Git Commit Guide — M2-M13 + Stage 1

> **RULE:** Claude never runs `git commit` or `git push`.  
> All commits are executed manually by Ajith.

---

## Pre-commit safety checks

Run these first. Each should return **no output** (empty = safe).

```powershell
# No AWS secret key IDs staged
git diff --staged | grep -i AKIA

# No backend.hcl staged (has real bucket name)
git diff --staged | grep backend.hcl

# No terraform.tfvars staged (has account-specific values)
git diff --staged | grep terraform.tfvars

# No .tfstate files staged
git diff --staged | grep .tfstate

# No plaintext secrets
git diff --staged | grep -iE "(password|secret|token|api_key)\s*="
```

If any return output, **do not commit** — investigate first.

---

## Commit sequence

### Step 1 — go to repo root

```powershell
cd C:\Users\Laptop\Documents\workspace\industrial-ai-platform-aws
```

### Step 2 — check current status

```powershell
git status
```

Expected: many new/modified files under `consumer/`, `edge/`, `tests/`, `terraform/`, `docs/`, `.github/`.

### Step 3 — stage everything

```powershell
git add -A
```

### Step 4 — review what's staged

```powershell
git diff --staged --stat
```

You should see something like:
```
consumer/storage_client.py        |  175 +++
consumer/checkpoint.py            |  ...
consumer/dynamo_checkpoint.py     |  ...
consumer/kinesis_consumer.py      |  ...
edge/base_producer.py             |  ...
edge/vehicle_producer.py          |  ...
edge/run_simulator.py             |  ...
edge/tcp_listener.py              |  ...       ← new
scripts/smoke_test_stage1.py      |  ...       ← new
terraform/environments/dev-stage1/main.tf      |  ...
terraform/environments/dev-stage1/backend.hcl.example | ...
docs/GIT_COMMIT_GUIDE.md          |  ...       ← new
...
```

**Not** staged (covered by .gitignore):
- `backend.hcl`
- `terraform.tfvars`
- `*.tfstate`, `.terraform/`
- `__pycache__/`, `*.pyc`

### Step 5 — commit

```powershell
git commit -m "feat: M2-M13 AWS platform + Stage 1 Terraform + smoke test + MP91 listener"
```

Or use a multi-line message:

```powershell
git commit -m "feat: M2-M13 AWS platform + Stage 1 Terraform

- M2: S3 storage client, DynamoDB checkpoint, Kinesis consumer/producer
- M3/M4: Terraform modules (data plane, security, network)
- M6: Databricks/UC Terraform module
- M7: DLT notebooks + DAB bundle
- M8: ML notebooks + Databricks job YAMLs
- M9: CI/CD GitHub Actions (AWS OIDC)
- M10: Observability doc + runbooks
- M11: Failure engineering test suite (moto)
- M12: Cross-cloud parity + security review docs
- M13: Production readiness report + README
- Stage 1: Minimal ephemeral AWS (Kinesis/S3/DDB/IAM) Terraform
- Add: scripts/smoke_test_stage1.py
- Add: edge/tcp_listener.py (Mictrack MP91)
- Fix: backend.hcl dynamodb_table → use_lockfile=true"
```

### Step 6 — push

```powershell
git push origin main
```

---

## What's in this commit (summary)

| Path | What |
|------|------|
| `consumer/` | S3 client, DynamoDB checkpoint, Kinesis consumer |
| `edge/` | KinesisProducer, vehicle simulator, MP91 TCP listener |
| `scripts/smoke_test_stage1.py` | End-to-end smoke test for Stage 1 |
| `terraform/environments/dev-stage1/` | Kinesis + S3 + DDB + IAM (Stage 1) |
| `terraform/bootstrap/` | Remote state bucket + DynamoDB lock |
| `terraform/modules/` | Reusable Terraform modules |
| `tests/` | 171 tests (unit + moto integration) |
| `.github/workflows/` | CI/CD pipelines (AWS OIDC) |
| `docs/` | AWS parity docs, runbooks, production readiness |
| `build_runbook.py` | Script to generate IAP_AWS_Ops_Runbook.xlsx |

## What's NOT committed (by design)

| File | Why |
|------|-----|
| `terraform/environments/dev-stage1/backend.hcl` | Contains real S3 bucket name |
| `terraform/environments/dev-stage1/terraform.tfvars` | Account-specific values |
| `terraform/environments/dev-stage1/stage1.tfplan` | Binary plan file |
| `terraform/environments/dev-stage1/.terraform/` | Provider cache |
| `*.tfstate` / `*.tfstate.backup` | Live state — never commit |
| `__pycache__/` | Python bytecode |
| `IAP_AWS_Ops_Runbook.xlsx` | Generated artifact — regenerate with `python build_runbook.py` |

---

## After the commit — next steps

1. **Activate AWS account** → complete registration in AWS console  
   (Billing → Complete registration → add payment method)

2. **Re-run Kinesis deploy** once account is activated:
   ```powershell
   cd terraform\environments\dev-stage1
   terraform plan "-var-file=terraform.tfvars" "-out=stage1.tfplan"
   terraform apply "stage1.tfplan"
   ```

3. **Run smoke test**:
   ```powershell
   set KINESIS_STREAM_NAME=iap-dev-telemetryhub
   set S3_BUCKET=iap-dev-lake-246568717136
   set DYNAMODB_TABLE=iap-dev-checkpoints
   set AWS_PROFILE=iap-dev
   set AWS_DEFAULT_REGION=ca-central-1
   python scripts/smoke_test_stage1.py
   ```

4. **Destroy Kinesis immediately after**:
   ```powershell
   terraform destroy "-var-file=terraform.tfvars" -target=aws_kinesis_stream.telemetry
   ```

5. **MP91 device arrives (~15 days)** → set up Koodo SIM, point to EC2, run:
   ```powershell
   python edge/tcp_listener.py
   ```
