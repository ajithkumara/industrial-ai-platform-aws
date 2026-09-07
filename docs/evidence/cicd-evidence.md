# cicd-evidence.md — Milestone 9 (CI/CD)

- **Date (UTC):** 2026-09-07
- **Workflows:** `.github/workflows/{python-tests,terraform,databricks,databricks-deploy}.yml`

## Design (mirrors the Azure workflow philosophy, AWS-native auth)

| Workflow | Triggers | Stages |
|---|---|---|
| python-tests | push/PR | setup Python 3.11 + Java 17 → `pip install` → `pytest tests/ -v` (unit/contract/DQ/ML/moto/Spark) → `pip-audit` dependency scan |
| terraform | push/PR on terraform/** | **AWS OIDC** role assume → `fmt -check` → `init -backend=false` + `validate` → **checkov** IaC scan → `plan` (PR) → PR plan comment → **apply** (main, `environment: dev` gate) |
| databricks | push/PR (no paths filter, required check) | `databricks bundle validate -t dev` (Databricks OAuth SP) |
| databricks-deploy | push on pipeline/ml paths | `bundle deploy -t dev` → smoke `bundle validate` (`environment: dev` gate) |

## E-M9-1 — No static credentials (Phase 11 requirement)

- `terraform.yml` authenticates via `aws-actions/configure-aws-credentials`
  with `role-to-assume: ${{ vars.AWS_CI_ROLE_ARN }}` and `permissions:
  id-token: write` — short-lived OIDC credentials, the AWS analogue of the
  Azure P1-08 OIDC change.
- `databricks.yml` uses a Databricks OAuth service principal
  (`DATABRICKS_CLIENT_ID` var + `DATABRICKS_CLIENT_SECRET` secret); no PAT
  committed.
- Grep for `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` in `.github/workflows/`
  → **zero matches.**

## E-M9-2 — Deploy gates

Both `apply` and `databricks-deploy` use `environment: dev`, so a merge to main
does not deploy until the environment's protection rules are satisfied. Infra
apply is `needs: validate`, so a failing validate/scan blocks deploy.

## E-M9-3 — Local proxies for the CI steps (actually executed here)

The CI steps were exercised locally where possible (the runner itself is NOT
EXECUTED — see below):

| CI step | Local proxy command | Result |
|---|---|---|
| pytest | `python3 -m pytest tests/ -q` | **166 passed, 11 skipped** |
| dependency scan | `pip-audit -r requirements.txt` | no known vulnerabilities |
| checkov | `checkov -d terraform` | 274 passed / 27 failed (accepted set documented) |
| hcl2 validate (fmt/validate proxy) | `python -c "import hcl2 ..."` | 49/49 .tf parse |
| workflow YAML | `yaml.safe_load` each | 4/4 valid |

## NOT EXECUTED (require GitHub + AWS/Databricks)

The workflows themselves run only on GitHub Actions against your AWS account +
Databricks workspace. `terraform fmt -check`/`validate`/`plan`/`apply`, the live
checkov-action, and `databricks bundle validate/deploy` are NOT EXECUTED here.
To run: open a PR (triggers terraform + python-tests + databricks validate);
merge to main (triggers apply + deploy behind the `dev` environment gate). Repo
variables/secrets to set first: `AWS_CI_ROLE_ARN`, `AWS_REGION`, `S3_BUCKET`,
`DATABRICKS_HOST`, `DATABRICKS_CLIENT_ID`, `DATABRICKS_CLIENT_SECRET`.
