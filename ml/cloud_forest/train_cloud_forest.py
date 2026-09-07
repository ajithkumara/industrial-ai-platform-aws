# Databricks notebook source
# train_cloud_forest.py — CloudForest: heavier cloud-side validation model
#
# Trains the cloud validation model used by HYBRID-mode escalation (see
# config/asset_types/cloud_validation.yml and
# ml/cloud_forest/score_escalations.py). This is a *heavier* Isolation
# Forest than the edge model (more trees, full feature set, no per-inference
# latency budget) -- NOT a different algorithm family. Swapping it for an
# autoencoder or ensemble later requires no change anywhere else in the
# platform: the event contract (edge_confidence, cloud_score,
# agrees_with_edge, ...) is what everything downstream depends on, not
# this specific model implementation. See the architectural note at the
# top of config/asset_types/cloud_validation.yml.
#
# Trained on industrial_ai.silver.silver_bearing_sensor_telemetry, which
# already carries per-window vibration features (rms, peak, crest,
# kurtosis, skew, variance, mean_abs) and the CWRU fault-class label --
# the SAME feature set the edge model was trained on, per the
# architecture doc's "lightweight edge model" description. Training on
# normal-only data mirrors the edge model's own unsupervised convention
# (Isolation Forest trained on normal data only, per Architecture v1.0
# Section 4.2).
#
# This is a plain Databricks notebook (no `import dlt`) intended to be
# run as a standalone, on-demand Databricks Job task -- training is not
# a continuous streaming operation and does not belong in the DLT
# pipeline. See databricks/resources/jobs/cloud_forest.yml.
#
# Requires scikit-learn and mlflow, both preinstalled on Databricks
# Runtime -- not added to requirements.txt, which covers only the local
# dev/CI environment (consumer, edge, tests), never Databricks notebook
# execution.

# COMMAND ----------

import mlflow
import mlflow.sklearn
import pandas as pd
from sklearn.ensemble import IsolationForest

# ---------------------------------------------------------------------------
# Job parameters (Databricks widgets) -- overridable per job run without
# editing this notebook. Defaults match the values used elsewhere in this
# repo (industrial_ai catalog, "cloud_forest_bearing" registered model
# name convention matches config/asset_types/cloud_validation.yml's
# cloud_model_version field).
# ---------------------------------------------------------------------------
dbutils.widgets.text("silver_table", "industrial_ai.silver.silver_bearing_sensor_telemetry")
dbutils.widgets.text("registered_model_name", "cloud_forest_bearing")
dbutils.widgets.text("n_estimators", "300")
dbutils.widgets.text("contamination", "auto")

SILVER_TABLE = dbutils.widgets.get("silver_table")
REGISTERED_MODEL_NAME = dbutils.widgets.get("registered_model_name")
N_ESTIMATORS = int(dbutils.widgets.get("n_estimators"))
CONTAMINATION = dbutils.widgets.get("contamination")
CONTAMINATION = "auto" if CONTAMINATION == "auto" else float(CONTAMINATION)

FEATURE_COLUMNS = ["rms", "peak", "crest", "kurtosis", "skew", "variance", "mean_abs"]

# COMMAND ----------
# Load features. Training-time only -- small enough (bearing telemetry,
# thesis evaluation scale) to bring into pandas rather than requiring a
# distributed training framework, and scikit-learn's IsolationForest has
# no native Spark equivalent worth adopting at this scale.

df = spark.table(SILVER_TABLE).select(*FEATURE_COLUMNS, "ground_truth_label")
pdf = df.toPandas().dropna(subset=FEATURE_COLUMNS)

normal_only = pdf[pdf["ground_truth_label"] == "normal"]
if len(normal_only) < 10:
    raise ValueError(
        f"Only {len(normal_only)} normal-labeled rows available in "
        f"{SILVER_TABLE} -- need more evaluation data landed before "
        "CloudForest can be meaningfully trained. Run the bearing "
        "sensor/inference smoke tests (tests/test_send_bearing_events.py) "
        "or a real evaluation scenario first."
    )

# COMMAND ----------
# Train. Heavier than the edge model by design: more trees than a
# resource-constrained edge device could run under a real-time budget,
# and no per-inference latency target -- this only ever runs
# asynchronously, on escalated events, never in the edge decision path.

model = IsolationForest(
    n_estimators=N_ESTIMATORS,
    max_features=1.0,
    contamination=CONTAMINATION,
    random_state=42,
    n_jobs=-1,
)
model.fit(normal_only[FEATURE_COLUMNS])

# COMMAND ----------
# Log + register via Databricks-managed MLflow -- the model registry
# score_escalations.py loads from at inference time
# (models:/cloud_forest_bearing/<stage or version>).

with mlflow.start_run(run_name="cloud_forest_train") as run:
    mlflow.log_param("n_estimators", N_ESTIMATORS)
    mlflow.log_param("contamination", CONTAMINATION)
    mlflow.log_param("feature_columns", ",".join(FEATURE_COLUMNS))
    mlflow.log_param("training_table", SILVER_TABLE)
    mlflow.log_metric("n_training_rows", len(normal_only))

    mlflow.sklearn.log_model(
        model,
        artifact_path="cloud_forest_model",
        registered_model_name=REGISTERED_MODEL_NAME,
    )

    print(
        f"CloudForest trained on {len(normal_only)} normal rows from "
        f"{SILVER_TABLE}, registered as '{REGISTERED_MODEL_NAME}' "
        f"(run_id={run.info.run_id})."
    )
