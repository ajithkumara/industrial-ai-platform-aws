# Databricks notebook source
# train_bearing_isolation_forest.py — Edge bearing anomaly baseline (H1)
#
# Trains the lightweight, time-domain-only Isolation Forest baseline on
# industrial_ai.gold.bearing_ml_features, using the recording-level,
# leakage-safe splits already computed there (see
# dlt/gold/bearing_ml_features.py and ml/feature_spec.py).
#
# THRESHOLD METHODOLOGY (frozen, do not change without updating this
# docstring and re-deriving every downstream metric):
#
#   TRAIN (is_training_eligible = true: normal recordings only)
#       -> fit IsolationForest on time-domain features only
#       -> unsupervised: ground_truth_label is NEVER used for fitting
#   VALIDATION (normal + fault recordings, labels visible)
#       -> score every row, transform to anomaly_score (higher = anomalous)
#       -> select threshold tau* = argmax_tau F1(tau) via
#          ml.bearing_model_common.select_threshold_by_max_f1
#       -> freeze tau*
#   TEST (held out, untouched by this script)
#       -> scored and evaluated ONLY by ml/evaluate_bearing_model.py,
#          exactly once, using the frozen tau* logged here. This script
#          does not load TEST rows at all -- there is nothing for it to
#          leak, structurally, not just by convention.
#
# Rationale for max-F1 as the selection criterion, and the caveat about
# when NOT to use it (asymmetric cost of missed faults vs. false alarms),
# is documented in the reviewer discussion this script implements --
# see docs/architecture/PLATFORM_THESIS_REVIEW_2026-08.md and the ML
# chapter draft. Changing the criterion (e.g. to max recall at a minimum
# precision, or an F-beta with beta>1) is a one-line change in the
# select_threshold call below plus a docstring update explaining why.
#
# Score-direction contract: this script uses the SAME sigmoid transform
# CloudForest uses (ml/cloud_forest/score_escalations.py) so anomaly_score
# means "higher = more anomalous" identically across edge, cloud, and
# every Gold table. See ml/bearing_model_common.py's module docstring.
#
# Plain Databricks notebook (no `import dlt`) intended to run as an
# on-demand Databricks Job task, mirroring ml/cloud_forest/train_cloud_forest.py's
# structure. Requires scikit-learn and mlflow (preinstalled on Databricks
# Runtime).

# COMMAND ----------

import sys

import mlflow
import mlflow.sklearn
from mlflow.models import infer_signature
from sklearn.ensemble import IsolationForest

# ---------------------------------------------------------------------------
# Job parameters (Databricks widgets)
#
# repo_root: unlike a DLT pipeline notebook (which resolves dlt/common via
# an explicit spark.conf value -- see dlt/silver/flatten_payloads.py's
# header comment on why __file__ doesn't work there), a plain Jobs
# notebook has no built-in way to find its own deployed location on
# sys.path. Passed in via the same ${workspace.file_path} bundle
# substitution the DLT pipeline already uses (see
# databricks/resources/pipelines/dlt.yml's asset_types_config_dir /
# dlt_common_dir configuration values) so `import ml.bearing_model_common`
# resolves against this job's own deployed copy of the repo, not whatever
# happens to be importable in the notebook's default path.
# ---------------------------------------------------------------------------
dbutils.widgets.text("repo_root", "")
dbutils.widgets.text("gold_table", "industrial_ai.gold.bearing_ml_features")
dbutils.widgets.text("dataset_run_id", "cwru_exp_001")
# Three-part Unity Catalog name required for model registration -- see
# terraform/modules/unity_catalog/schema.tf's "ml" schema (added 2026-08
# specifically for this; only bronze/silver/gold previously existed).
dbutils.widgets.text("registered_model_name", "industrial_ai.ml.edge_bearing_isolation_forest")
dbutils.widgets.text("n_estimators", "100")
dbutils.widgets.text("max_samples", "auto")
dbutils.widgets.text("contamination", "auto")
dbutils.widgets.text("random_seed", "42")

REPO_ROOT = dbutils.widgets.get("repo_root")
if REPO_ROOT and REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from ml.bearing_model_common import (  # noqa: E402  (must follow sys.path fixup above)
    FEATURE_COLUMNS,
    SCORE_SIGMOID_K,
    raw_scores_to_anomaly_scores,
    select_threshold_by_max_f1,
)

GOLD_TABLE = dbutils.widgets.get("gold_table")
DATASET_RUN_ID = dbutils.widgets.get("dataset_run_id")
REGISTERED_MODEL_NAME = dbutils.widgets.get("registered_model_name")
N_ESTIMATORS = int(dbutils.widgets.get("n_estimators"))
MAX_SAMPLES = dbutils.widgets.get("max_samples")
MAX_SAMPLES = "auto" if MAX_SAMPLES == "auto" else float(MAX_SAMPLES)
CONTAMINATION = dbutils.widgets.get("contamination")
CONTAMINATION = "auto" if CONTAMINATION == "auto" else float(CONTAMINATION)
RANDOM_SEED = int(dbutils.widgets.get("random_seed"))

THRESHOLD_SELECTION_METHOD = "validation_max_f1"

FEATURE_SET_VERSION = "bearing-features-v1"  # must match dlt/gold/bearing_ml_features.py
WINDOW_SIZE = 2048       # must match ml/cwru_loader.py::WINDOW_SAMPLES
SAMPLING_RATE_HZ = 12000  # must match ml/cwru_loader.py::SAMPLING_RATE_HZ

# COMMAND ----------
# Load TRAIN and VALIDATION only. TEST rows are never queried by this
# script -- see module docstring. If a future refactor adds a TEST branch
# here, that is a methodology violation; catch it in review, not just here.

base = spark.table(GOLD_TABLE).filter(f"dataset_run_id = '{DATASET_RUN_ID}'")

train_pdf = (
    base.filter("is_training_eligible = true")
    .select(*FEATURE_COLUMNS)
    .toPandas()
    .dropna(subset=FEATURE_COLUMNS)
)

validation_pdf = (
    base.filter("dataset_split = 'VALIDATION'")
    .select(*FEATURE_COLUMNS, "is_actual_anomaly", "source_file")
    .toPandas()
    .dropna(subset=FEATURE_COLUMNS)
)

if len(train_pdf) < 10:
    raise ValueError(
        f"Only {len(train_pdf)} training-eligible rows found in {GOLD_TABLE} "
        f"for dataset_run_id='{DATASET_RUN_ID}'. Check the CWRU ingestion "
        f"and Gold pipeline ran successfully before training."
    )
if len(validation_pdf) == 0:
    raise ValueError(
        f"No VALIDATION rows found in {GOLD_TABLE} for "
        f"dataset_run_id='{DATASET_RUN_ID}' -- cannot select a threshold "
        f"without validation data."
    )

print(f"TRAIN (is_training_eligible): {len(train_pdf)} rows")
print(f"VALIDATION: {len(validation_pdf)} rows "
      f"({validation_pdf['is_actual_anomaly'].sum()} actual anomalies, "
      f"{len(validation_pdf) - validation_pdf['is_actual_anomaly'].sum()} actual normal)")

# COMMAND ----------
# Fit. Unsupervised: ground_truth_label / is_actual_anomaly are never
# passed to .fit(), only to threshold selection below.

model = IsolationForest(
    n_estimators=N_ESTIMATORS,
    max_samples=MAX_SAMPLES,
    contamination=CONTAMINATION,
    random_state=RANDOM_SEED,
    n_jobs=-1,
)
model.fit(train_pdf[FEATURE_COLUMNS])

# COMMAND ----------
# Score VALIDATION, transform to anomaly_score, select + freeze threshold.

raw_scores = model.decision_function(validation_pdf[FEATURE_COLUMNS])
validation_pdf["anomaly_score"] = raw_scores_to_anomaly_scores(raw_scores)

selection = select_threshold_by_max_f1(
    anomaly_scores=validation_pdf["anomaly_score"].tolist(),
    is_actual_anomaly=validation_pdf["is_actual_anomaly"].tolist(),
)

print(
    f"Selected threshold tau*={selection.threshold:.6f} "
    f"(evaluated {selection.candidates_evaluated} candidate thresholds on VALIDATION)"
)
print(f"VALIDATION @ tau*: {selection.validation_confusion.as_dict()}")

# COMMAND ----------
# Log everything to MLflow: params needed to reproduce, the frozen
# threshold (both as a param, for quick browsing, and as a JSON artifact,
# for evaluate_bearing_model.py to load programmatically), and the
# VALIDATION-only metrics that justified the choice.

with mlflow.start_run(run_name="edge_bearing_isolation_forest_train") as run:
    mlflow.log_param("dataset_run_id", DATASET_RUN_ID)
    mlflow.log_param("gold_table", GOLD_TABLE)
    mlflow.log_param("feature_set_version", FEATURE_SET_VERSION)
    mlflow.log_param("window_size", WINDOW_SIZE)
    mlflow.log_param("sampling_rate_hz", SAMPLING_RATE_HZ)
    mlflow.log_param("feature_columns", ",".join(FEATURE_COLUMNS))
    mlflow.log_param("n_estimators", N_ESTIMATORS)
    mlflow.log_param("max_samples", MAX_SAMPLES)
    mlflow.log_param("contamination", CONTAMINATION)
    mlflow.log_param("random_seed", RANDOM_SEED)
    mlflow.log_param("score_sigmoid_k", SCORE_SIGMOID_K)
    mlflow.log_param("threshold_selection_method", THRESHOLD_SELECTION_METHOD)
    mlflow.log_param("selected_threshold", selection.threshold)

    mlflow.log_metric("n_training_rows", len(train_pdf))
    mlflow.log_metric("n_validation_rows", len(validation_pdf))
    mlflow.log_metric("validation_precision", selection.validation_confusion.precision)
    mlflow.log_metric("validation_recall", selection.validation_confusion.recall)
    mlflow.log_metric("validation_f1", selection.validation_confusion.f1)
    mlflow.log_metric("validation_tp", selection.validation_confusion.tp)
    mlflow.log_metric("validation_fp", selection.validation_confusion.fp)
    mlflow.log_metric("validation_fn", selection.validation_confusion.fn)
    mlflow.log_metric("validation_tn", selection.validation_confusion.tn)

    # Artifact form of the frozen threshold + everything evaluate_bearing_model.py
    # needs to reproduce this exact scoring pipeline without re-deriving it.
    #
    # BUGFIX: previously wrote to a hardcoded "/tmp/frozen_threshold.json"
    # then log_artifact()'d it, which raised PermissionError on serverless
    # compute (serverless notebook execution does not grant write access to
    # the container's root /tmp). mlflow.log_dict() serialises the dict to
    # a run artifact directly, with no local filesystem write at all --
    # simpler and portable across every compute type.
    frozen = {
        "dataset_run_id": DATASET_RUN_ID,
        "feature_columns": FEATURE_COLUMNS,
        "score_sigmoid_k": SCORE_SIGMOID_K,
        "threshold_selection_method": THRESHOLD_SELECTION_METHOD,
        "selected_threshold": selection.threshold,
        "validation_metrics": selection.validation_confusion.as_dict(),
    }
    mlflow.log_dict(frozen, "frozen_threshold.json")

    # BUGFIX: Unity Catalog model registry rejects any model logged
    # without a signature ("Model passed for registration did not contain
    # any signature metadata") -- unlike the legacy workspace registry,
    # UC validates this at registration time, not just at serving time.
    #
    # Output is inferred from model.decision_function(), NOT model.predict():
    # the actual scoring contract (ml/evaluate_bearing_model.py and
    # ml/cloud_forest/score_escalations.py) consumes the continuous
    # decision_function score and passes it through
    # raw_scores_to_anomaly_scores(). model.predict()'s +1/-1 label is
    # never used anywhere in this platform, so signing the model against it
    # would document an interface no consumer actually calls. Inferring
    # from real TRAIN data means the signature can never drift from what
    # the model truly accepts/returns.
    signature = infer_signature(
        train_pdf[FEATURE_COLUMNS], model.decision_function(train_pdf[FEATURE_COLUMNS])
    )

    mlflow.sklearn.log_model(
        model,
        artifact_path="edge_bearing_isolation_forest_model",
        registered_model_name=REGISTERED_MODEL_NAME,
        signature=signature,
        input_example=train_pdf[FEATURE_COLUMNS].head(5),
    )

    print(
        f"Trained on {len(train_pdf)} normal TRAIN rows, threshold frozen at "
        f"{selection.threshold:.6f} using VALIDATION F1={selection.validation_confusion.f1:.4f}. "
        f"Registered as '{REGISTERED_MODEL_NAME}' (run_id={run.info.run_id}).\n"
        f"Run evaluate_bearing_model.py with run_id={run.info.run_id} to get the "
        f"final, one-time TEST evaluation."
    )
