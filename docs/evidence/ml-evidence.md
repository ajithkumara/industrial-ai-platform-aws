# ml-evidence.md — Milestone 8 (ML / MLOps)

- **Date (UTC):** 2026-09-07
- **Commands:**
  `python3 -m pytest tests/test_train_bearing_isolation_forest_contract.py tests/test_ml_reproducibility.py -v`
- **Result:** **17 passed** (13 contract + 4 reproducibility/leakage).

## Code parity

All ML notebooks are **byte-identical** to the Azure reference:
`ml/train_bearing_isolation_forest.py`, `ml/evaluate_bearing_model.py`,
`ml/cloud_forest/train_cloud_forest.py`, `ml/cloud_forest/score_escalations.py`,
`notebooks/maintenance/delta_optimize_vacuum.py`. The pure-Python spec/scoring/
loader (`feature_spec.py`, `bearing_model_common.py`, `cwru_loader.py`) were
copied verbatim in M1.

**One adapted file:** `notebooks/mlops/mlflow_artifact_backup.py` — the backup
destination changed from ADLS `abfss://` to `s3://<bucket>/...` (bucket supplied
via Job base_parameter `backup_bucket`, sourced from Terraform output
`s3_bucket`). Logic otherwise unchanged.

**Job wiring:** `cloud_forest.yml` `score_escalations` `bronze_path` →
`s3://${var.s3_bucket}/raw/telemetry/`; `mlflow_backup.yml` →
`backup_bucket: ${var.s3_bucket}`. All four jobs wired into `databricks.yml`.
No residual `abfss://` or `storage_account_name` in jobs/ or notebooks/mlops.

## E-M8-1 — Training/eval contract (source assertions, 13)

`test_train_bearing_isolation_forest_contract.py` (ported verbatim) asserts on
the actual notebook source: MLflow signature inferred from `decision_function`
(not `predict`); three-part UC model name `industrial_ai.ml.*`; frozen threshold
via `log_dict` (no `/tmp` write); training never reads TEST; threshold selected
on VALIDATION only; fit uses only `is_training_eligible` rows; eval is the only
script reading TEST and does no threshold search; both scripts share the sigmoid
transform. All PASS — the reproducibility/leakage discipline is intact in the
AWS copy.

## E-M8-2 — Reproducibility + leakage (real sklearn, 4)

`test_ml_reproducibility.py`:
- **Deterministic model:** IsolationForest(seed=42) → identical anomaly scores
  across runs.
- **Deterministic threshold:** same VALIDATION → identical frozen threshold +
  confusion (F1 > 0.8 on separable synthetic data), via the real
  `select_threshold_by_max_f1`.
- **Recording-level split isolation + TRAIN-normal-only:** via the real
  `feature_spec.assign_split` — TRAIN contains only normal recordings;
  `is_training_eligible == (TRAIN and normal)`.
- **Fault recordings never in TRAIN** across recording counts 1..7.

## Reproducibility contract (Phase 7)

`dataset_run_id` + `feature_set_version` + fixed `random_seed=42` + frozen
threshold (loaded from the MLflow run artifact, never recomputed) → identical
TEST metrics. The training notebook logs all of these (verified E-M8-1).

## NOT EXECUTED (require Databricks + MLflow)

Live train/eval/score runs, MLflow tracking/registry, and the model artifact
S3 backup run are NOT EXECUTED (no Databricks workspace/MLflow here). Commands:
`databricks bundle run bearing_isolation_forest_train -t dev`, then
`... bearing_isolation_forest_evaluate -t dev --params train_run_id=<id>`.
Notebook parity + offline reproducibility above verify the methodology; the gap
is only the live cluster run.
