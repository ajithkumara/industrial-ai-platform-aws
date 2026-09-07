# Databricks notebook source
# mlflow_artifact_backup.py — Daily MLflow model artifact backup (AWS)
#
# P1-15: Copies Production and Staging registered model artifacts to a
# versioned S3 path that is independent of the Databricks MLflow store.
# This protects against:
#   - Accidental model deletion via the UI or API
#   - Workspace corruption / data loss events
#   - Account/workspace migration (backup survives even if workspace is recreated)
#
# AWS translation of the Azure reference: the backup destination is S3 instead
# of ADLS abfss://. The S3 bucket is supplied as a Job base_parameter
# (backup_bucket), sourced from the core Terraform output `s3_bucket`. Access is
# via the cluster's instance profile / UC credential — no storage-account
# spark config needed.
#
# Backup path structure:
#   s3://<bucket>/<prefix>/<date>/<model>/<version>/

from datetime import datetime, timezone

import mlflow
from mlflow.tracking import MlflowClient

# ── Parameters ───────────────────────────────────────────────────────────────
_widget_names = [w.name for w in dbutils.widgets.getAll()]
backup_bucket = dbutils.widgets.get("backup_bucket") if "backup_bucket" in _widget_names else ""
backup_prefix = dbutils.widgets.get("backup_prefix") if "backup_prefix" in _widget_names else "mlflow-backup"

if not backup_bucket:
    raise ValueError(
        "backup_bucket is empty -- supply it via the Job base_parameters "
        "(sourced from the core Terraform output s3_bucket). Refusing to run "
        "without an explicit destination bucket."
    )

STAGES_TO_BACKUP = {"Production", "Staging"}
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")

client = MlflowClient()
models = client.search_registered_models()

backed_up = []
errors = []

for model in models:
    for mv in client.get_latest_versions(model.name, stages=list(STAGES_TO_BACKUP)):
        src_uri = mv.source  # e.g. dbfs:/databricks/mlflow-tracking/.../artifacts/model
        backup_path = (
            f"s3://{backup_bucket}/{backup_prefix}/{TODAY}/{model.name}/v{mv.version}"
        )
        try:
            print(f"Copying {model.name} v{mv.version} ({mv.current_stage}) → {backup_path}")
            dbutils.fs.cp(src_uri, backup_path, recurse=True)
            backed_up.append(f"{model.name} v{mv.version} ({mv.current_stage})")
            print(f"  ✓ done")
        except Exception as e:
            msg = f"FAILED {model.name} v{mv.version}: {e}"
            print(msg)
            errors.append(msg)

print(f"\nBacked up {len(backed_up)} model version(s):")
for item in backed_up:
    print(f"  • {item}")

if errors:
    raise RuntimeError(
        f"MLflow backup failed for {len(errors)} model version(s):\n" + "\n".join(errors)
    )

print("MLflow artifact backup complete.")
