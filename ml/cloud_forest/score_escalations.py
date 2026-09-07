# Databricks notebook source
# score_escalations.py — CloudForest: score HYBRID-mode escalations
#
# For every silver_bearing_inference_results row in HYBRID mode that has
# not already been validated, loads the registered CloudForest model
# (see train_cloud_forest.py), re-scores the event's vibration features
# from silver_bearing_sensor_telemetry, and writes one cloud_validation
# record per escalation into the same raw ADLS landing path the consumer
# uses -- so it flows through the existing Bronze Auto Loader -> Silver
# dedup -> config-driven flatten pipeline with zero special-casing (see
# config/asset_types/cloud_validation.yml for the payload contract).
#
# ARCHITECTURAL INVARIANT: this job is asynchronous, batch, and
# read-only with respect to the edge decision. It never blocks, delays,
# or overrides anything the edge orchestrator already decided -- it
# writes a *second opinion*, recorded after the fact, purely for
# research/enrichment (research gap claim C4 / RQ2). If this job is
# late, down, or wrong, the edge system's real-time behavior and
# thesis hypotheses H1/H2/H3 are completely unaffected.
#
# Correlation: silver_bearing_inference_results and
# silver_bearing_sensor_telemetry are two separate NATS-bridged streams
# for "the same underlying reading" (see edge/nats_bearing_bridge.py's
# translate_sensor_record/translate_inference_record docstrings) -- they
# share device_id + seq, which is the join key used below.
#
# Plain Databricks notebook (no `import dlt`) intended to run as an
# on-demand / scheduled Databricks Job task, not inside the DLT
# pipeline -- see databricks/resources/jobs/cloud_forest.yml.

# COMMAND ----------

import json
import time
import uuid
from datetime import UTC, datetime

import mlflow
import mlflow.sklearn
from pyspark.sql import functions as F

# ---------------------------------------------------------------------------
# Job parameters (Databricks widgets)
# ---------------------------------------------------------------------------
dbutils.widgets.text("registered_model_name", "cloud_forest_bearing")
dbutils.widgets.text("model_stage_or_version", "latest")
dbutils.widgets.text("anomaly_threshold", "0.60")
# PORTABILITY: no hardcoded storage account. The deployed Job supplies
# bronze_path from bundle variables (see databricks/resources/jobs/
# cloud_forest.yml, sourced from the Terraform output storage_account_name).
# Empty default => fail fast if run manually without supplying it, rather than
# silently targeting a decommissioned account.
dbutils.widgets.text("bronze_path", "")

REGISTERED_MODEL_NAME = dbutils.widgets.get("registered_model_name")
MODEL_STAGE_OR_VERSION = dbutils.widgets.get("model_stage_or_version")
ANOMALY_THRESHOLD = float(dbutils.widgets.get("anomaly_threshold"))
BRONZE_PATH = dbutils.widgets.get("bronze_path")
if not BRONZE_PATH:
    raise ValueError(
        "bronze_path is empty -- supply it via the Job base_parameters "
        "(databricks/resources/jobs/cloud_forest.yml sources it from the "
        "Terraform output storage_account_name)."
    )

FEATURE_COLUMNS = ["rms", "peak", "crest", "kurtosis", "skew", "variance", "mean_abs"]

# Fixed namespace so the same escalation always produces the same
# cloud_validation event_id -- reprocessing the same escalation (e.g. job
# retried) is collapsed by Silver's dedup-by-event_id, exactly like the
# NATS bridge's deterministic ids (see edge/nats_bearing_bridge.py).
_CLOUD_FOREST_NAMESPACE = uuid.UUID("9a2f4c6e-3b1d-4a8e-9c7f-1d2e3f4a5b6c")

# COMMAND ----------
# Load the model. "latest" resolves the highest version number rather
# than requiring a Production-stage alias to already be set up --
# convenient for thesis-scale evaluation runs where a full staging
# workflow (Roadmap V2 scope) doesn't exist yet.

client = mlflow.tracking.MlflowClient()
if MODEL_STAGE_OR_VERSION == "latest":
    versions = client.search_model_versions(f"name='{REGISTERED_MODEL_NAME}'")
    if not versions:
        raise ValueError(
            f"No registered versions found for model "
            f"'{REGISTERED_MODEL_NAME}'. Run train_cloud_forest.py first."
        )
    model_version = str(max(int(v.version) for v in versions))
    model_uri = f"models:/{REGISTERED_MODEL_NAME}/{model_version}"
else:
    model_version = MODEL_STAGE_OR_VERSION
    model_uri = f"models:/{REGISTERED_MODEL_NAME}/{MODEL_STAGE_OR_VERSION}"

cloud_model = mlflow.sklearn.load_model(model_uri)
CLOUD_MODEL_VERSION_TAG = f"{REGISTERED_MODEL_NAME}-v{model_version}"

# COMMAND ----------
# Find escalations that need scoring: HYBRID-mode inference events not
# already present in silver_cloud_validation_results (anti-join on the
# correlation key), joined to their feature vector.

inference = spark.table("industrial_ai.silver.silver_bearing_inference_results").filter(
    F.col("mode") == "HYBRID"
)

already_validated = spark.table(
    "industrial_ai.silver.silver_cloud_validation_results"
).select(F.col("source_event_id"))

pending = inference.join(
    already_validated,
    inference.event_id == already_validated.source_event_id,
    how="left_anti",
)

sensor = spark.table("industrial_ai.silver.silver_bearing_sensor_telemetry").select(
    "device_id", "seq", *FEATURE_COLUMNS
)

to_score = pending.join(sensor, on=["device_id", "seq"], how="inner")

to_score_pdf = to_score.select(
    "event_id",
    "device_id",
    "mode",
    "anomaly",
    "anomaly_score",
    "edge_confidence",
    "model_version",
    *FEATURE_COLUMNS,
).toPandas()

print(f"{len(to_score_pdf)} HYBRID escalation(s) pending CloudForest validation.")

# COMMAND ----------
# Score + build cloud_validation events.

events = []

if len(to_score_pdf) > 0:
    start = time.perf_counter()
    raw_scores = cloud_model.decision_function(to_score_pdf[FEATURE_COLUMNS])
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    per_row_latency_ms = elapsed_ms / len(to_score_pdf)

    # Same normalisation convention as the edge Inference Engine
    # (Architecture v1.0 Section 4.2): raw decision_function score ->
    # 0-1 anomaly score via sigmoid, so edge_score and cloud_score are
    # directly comparable in gold.escalation_efficacy.
    cloud_scores = 1.0 / (1.0 + pow(2.718281828, raw_scores * 5.0))

    for (_, row), cloud_score in zip(to_score_pdf.iterrows(), cloud_scores):
        cloud_anomaly = bool(cloud_score > ANOMALY_THRESHOLD)
        edge_anomaly = bool(row["anomaly"])
        agrees_with_edge = cloud_anomaly == edge_anomaly

        payload = {
            "source_event_id": row["event_id"],
            "edge_anomaly": edge_anomaly,
            "edge_score": float(row["anomaly_score"]) if row["anomaly_score"] is not None else None,
            "edge_confidence": (
                float(row["edge_confidence"]) if row["edge_confidence"] is not None else None
            ),
            "cloud_anomaly": cloud_anomaly,
            "cloud_score": float(cloud_score),
            "cloud_decision": "anomaly" if cloud_anomaly else "normal",
            "agrees_with_edge": agrees_with_edge,
            "edge_model_version": row["model_version"] or "unversioned",
            "cloud_model_version": CLOUD_MODEL_VERSION_TAG,
            "validation_latency_ms": per_row_latency_ms,
            "mode": row["mode"],
        }

        events.append(
            {
                "event_id": str(
                    uuid.uuid5(_CLOUD_FOREST_NAMESPACE, row["event_id"])
                ),
                "device_id": row["device_id"],
                "asset_type": "cloud_validation",
                "timestamp": datetime.now(UTC).isoformat(),
                # Disagreement is the interesting case -- route it at
                # higher priority so it's easy to find downstream.
                "priority": "high" if not agrees_with_edge else "normal",
                "schema_version": "1.0.0",
                "payload": payload,
            }
        )

# COMMAND ----------
# Write, in the same JSONL-per-batch shape and partition layout the
# consumer's StorageClient uses (raw/telemetry/year=/month=/day=/), so
# Bronze Auto Loader picks these up identically to Event-Hub-sourced
# telemetry -- no separate ingestion path to maintain.

if events:
    now = datetime.now(UTC)
    directory = f"{BRONZE_PATH.rstrip('/')}/year={now.year}/month={now.month:02}/day={now.day:02}"
    filename = f"cloud_validation_{now.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.jsonl"
    file_path = f"{directory}/{filename}"

    body = "\n".join(json.dumps(e, separators=(",", ":"), ensure_ascii=False) for e in events)
    dbutils.fs.put(file_path, body, overwrite=True)

    n_disagreements = sum(1 for e in events if e["priority"] == "high")
    print(
        f"Wrote {len(events)} cloud_validation event(s) to '{file_path}' "
        f"({n_disagreements} edge/cloud disagreement(s))."
    )
else:
    print("No pending escalations -- nothing written.")
