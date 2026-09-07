# CICD_BEHAVIOUR.md — Current Azure Platform

> Phase 0I deliverable. Every GitHub Actions workflow and its behaviour.

## Workflows (`.github/workflows/`)

### `ci.yml` — "CI/CD" (main Terraform plan/apply + bundle deploy)
- Triggers: PR + push to `main` on `terraform/**`, `databricks/**`, `dlt/**`,
  `databricks.yml`.
- Auth: **GitHub OIDC [P1-08]** — `ARM_USE_OIDC=true`, `ARM_CLIENT_ID/
  TENANT_ID/SUBSCRIPTION_ID` from repo **variables**; `id-token: write`.
- Job `terraform-plan` (PR only): init (backend.hcl), validate, `plan`
  targeting the module set (excludes `module.databricks` — UC needs
  metastore admin the CI SP lacks). **Posts the real plan diff to the PR
  [P1-17]** in a collapsible block, truncated at 60k chars.
- Job `terraform-apply` (push to main, `environment: dev`): apply the same
  targets, export TF outputs, `databricks bundle deploy -t dev` (Azure SP
  auth, DATABRICKS_TOKEN blanked). **Smoke test [P1-16]**: `databricks bundle
  validate -t dev`.

### `terraform.yml` — "Terraform CI"
- Triggers: PR + push on `terraform/**`. Job: `terraform init -backend=false`
  + `terraform validate` (dev). Lightweight validation gate.

### `databricks_deploy.yml` — "Databricks CI"
- Triggers: PR + push to `main`, **no `paths:` filter** (it is a required
  status check; a filtered required check reports permanently "pending" and
  blocks merges on unrelated PRs). Runs `databricks bundle validate` (Azure
  SP auth: `ARM_CLIENT_ID/SECRET/TENANT_ID` from secrets, `DATABRICKS_HOST`
  from vars, `BUNDLE_VAR_storage_account_name` from vars).

### `ci-cd.yml` — "Python Tests"
- Triggers: PR + push to `main`. Python 3.11, `pip install -r
  requirements.txt`, `python -m pytest tests/ -v`.

## Deployment ordering

Terraform infra (plan on PR → apply on merge) → export outputs → Databricks
bundle deploy → smoke validate. Python tests gate independently.

## AWS impact

- `ci-cd.yml` (Python tests) — **near-verbatim** (add boto3/moto deps; keep
  pytest). Tests are cloud-light.
- `ci.yml` — **adapted**: Azure OIDC → **AWS OIDC** via
  `aws-actions/configure-aws-credentials` (`role-to-assume`, `id-token:
  write`); `terraform plan/apply` with S3 backend; `ARM_*` env → AWS region/
  role. Keep the PR-plan-diff [P1-17] and smoke-test [P1-16] steps. Add
  **ECR build/push** (consumer container) and **security scanning** (e.g.
  `tfsec`/`checkov` + image scan) per Phase 11.
- `terraform.yml` — **adapted** (validate against AWS provider).
- `databricks_deploy.yml` — **adapted**: same bundle validate, Databricks-on-AWS
  auth (Databricks OAuth SP or workspace token via AWS secret); keep the
  no-paths-filter required-check semantics. Classification: **AZURE-SPECIFIC
  auth translation; workflow philosophy preserved.**
