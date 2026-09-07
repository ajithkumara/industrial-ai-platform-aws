# Databricks notebook source
# evaluate_bearing_model.py — ONE-TIME frozen-threshold TEST evaluation
#
# Loads the model and frozen threshold produced by a specific
# train_bearing_isolation_forest.py run (via its MLflow run_id), scores
# the held-out TEST split of industrial_ai.gold.bearing_ml_features, and
# reports final TP/FP/FN/TN/precision/recall/F1.
#
# METHODOLOGY DISCIPLINE: this script performs NO threshold search. The
# threshold comes from the training run's logged artifact
# (frozen_threshold.json) and is applied exactly once. If you find
# yourself wanting to try several thresholds against TEST results and
# pick the best-looking one, stop -- that silently turns TEST into a
# second validation set and invalidates the reported metrics. Go back to
# train_bearing_isolation_forest.py, change the selection criterion there
# (still using only VALIDATION), retrain, and only then re-run this
# script once against the new frozen threshold.
#
# STATISTICAL CAVEAT (carried over from ml/cwru_loader.py): TEST here is
# ~230-240 WINDOWS drawn from a much smaller number of independent
# RECORDINGS. Report recording-level context (how many distinct
# source_file values contributed to TEST) alongside the window-level
# metrics below -- do not present window count as if it were the
# effective sample size in the thesis evaluation chapter.
#
# Plain Databricks notebook (no `import dlt`), run as an on-demand
# Databricks Job task after train_bearing_isolation_forest.py has
# completed and logged a run.

# COMMAND ----------

import json
import sys

import mlflow
import mlflow.sklearn

# ---------------------------------------------------------------------------
# Job parameters (Databricks widgets)
#
# repo_root: same sys.path fixup as train_bearing_isolation_forest.py --
# a plain Jobs notebook has no built-in way to find its own deployed
# location, so `import ml.bearing_model_common` needs this passed in via
# the ${workspace.file_path} bundle substitution. See that script's
# header comment for the full rationale.
# ---------------------------------------------------------------------------
dbutils.widgets.text("repo_root", "")
dbutils.widgets.text("train_run_id", "")  # required: run_id printed by train_bearing_isolation_forest.py
dbutils.widgets.text("gold_table", "industrial_ai.gold.bearing_ml_features")

REPO_ROOT = dbutils.widgets.get("repo_root")
if REPO_ROOT and REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from ml.bearing_model_common import confusion_at_threshold, raw_scores_to_anomaly_scores  # noqa: E402

TRAIN_RUN_ID = dbutils.widgets.get("train_run_id")
GOLD_TABLE = dbutils.widgets.get("gold_table")

if not TRAIN_RUN_ID:
    raise ValueError(
        "train_run_id widget is required -- pass the run_id printed at the "
        "end of train_bearing_isolation_forest.py. This script deliberately "
        "does not default to 'latest run' so a TEST evaluation is always "
        "traceable to one specific, deliberate training run."
    )

# COMMAND ----------
# Load the frozen threshold + model from the specified training run.
# Both are loaded from MLflow, not recomputed, so this script cannot
# silently drift from what was actually frozen at training time.

client = mlflow.tracking.MlflowClient()
local_artifact_dir = client.download_artifacts(TRAIN_RUN_ID, "frozen_threshold.json")
with open(local_artifact_dir) as f:
    frozen = json.load(f)

DATASET_RUN_ID = frozen["dataset_run_id"]
FEATURE_COLUMNS = frozen["feature_columns"]
THRESHOLD = frozen["selected_threshold"]

model_uri = f"runs:/{TRAIN_RUN_ID}/edge_bearing_isolation_forest_model"
model = mlflow.sklearn.load_model(model_uri)

print(
    f"Loaded model + frozen threshold={THRESHOLD:.6f} from train run "
    f"{TRAIN_RUN_ID} (dataset_run_id='{DATASET_RUN_ID}', selection "
    f"method='{frozen['threshold_selection_method']}', VALIDATION "
    f"F1={frozen['validation_metrics']['f1']:.4f})."
)

# COMMAND ----------
# Load TEST rows ONLY -- this is the first and only point in the pipeline
# where TEST feature vectors and labels are read.

test_pdf = (
    spark.table(GOLD_TABLE)
    .filter(f"dataset_run_id = '{DATASET_RUN_ID}' AND dataset_split = 'TEST'")
    .select(*FEATURE_COLUMNS, "is_actual_anomaly", "source_file")
    .toPandas()
    .dropna(subset=FEATURE_COLUMNS)
)

if len(test_pdf) == 0:
    raise ValueError(
        f"No TEST rows found in {GOLD_TABLE} for dataset_run_id='{DATASET_RUN_ID}'."
    )

n_recordings = test_pdf["source_file"].nunique()
print(
    f"TEST: {len(test_pdf)} windows from {n_recordings} independent recordings "
    f"({test_pdf['is_actual_anomaly'].sum()} actual anomalies, "
    f"{len(test_pdf) - test_pdf['is_actual_anomaly'].sum()} actual normal)."
)

# COMMAND ----------
# Score + apply the frozen threshold exactly once. No search, no retry
# loop over candidate thresholds here -- see module docstring.

raw_scores = model.decision_function(test_pdf[FEATURE_COLUMNS])
test_pdf["anomaly_score"] = raw_scores_to_anomaly_scores(raw_scores)

confusion = confusion_at_threshold(
    anomaly_scores=test_pdf["anomaly_score"].tolist(),
    is_actual_anomaly=test_pdf["is_actual_anomaly"].tolist(),
    threshold=THRESHOLD,
)

result = confusion.as_dict()

# COMMAND ----------
# Log as a child run linked to the training run, and print the final
# report. This run's metrics are the ones that belong in the thesis
# evaluation chapter -- VALIDATION metrics logged by the training run are
# for threshold justification only, never reported as generalization
# performance.

with mlflow.start_run(run_name="edge_bearing_isolation_forest_test_eval") as run:
    mlflow.set_tag("parent_train_run_id", TRAIN_RUN_ID)
    mlflow.log_param("dataset_run_id", DATASET_RUN_ID)
    mlflow.log_param("frozen_threshold", THRESHOLD)
    mlflow.log_param("threshold_selection_method", frozen["threshold_selection_method"])
    mlflow.log_metric("n_test_windows", len(test_pdf))
    mlflow.log_metric("n_test_recordings", n_recordings)
    for k, v in result.items():
        mlflow.log_metric(f"test_{k}", v)

    print("=" * 60)
    print("FINAL TEST EVALUATION (frozen threshold, applied once)")
    print("=" * 60)
    print(f"dataset_run_id:        {DATASET_RUN_ID}")
    print(f"train_run_id:          {TRAIN_RUN_ID}")
    print(f"frozen threshold:      {THRESHOLD:.6f}")
    print(f"test windows:          {len(test_pdf)}")
    print(f"test recordings:       {n_recordings}  <-- effective sample size, not {len(test_pdf)}")
    print(f"TP={result['tp']}  FP={result['fp']}  FN={result['fn']}  TN={result['tn']}")
    print(f"precision:             {result['precision']:.4f}")
    print(f"recall:                {result['recall']:.4f}")
    print(f"F1:                    {result['f1']:.4f}")
    print(f"(eval run_id={run.info.run_id})")
