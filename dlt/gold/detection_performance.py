# Databricks notebook source
# detection_performance.py — Gold Layer (DLT): Edge Detection Performance
#
# Reads the standardized Silver bearing_inference table (config-driven,
# see config/asset_types/bearing_inference.yml) and computes precision /
# recall / F1 / inference-latency percentiles per operational mode and
# model_version, comparing the edge model's prediction (`anomaly`)
# against the dataset's ground-truth fault label (`ground_truth_label`).
#
# DEPENDS ON the 2026-08 rename in config/asset_types/bearing_inference.yml
# (payload.label -> ground_truth_label, not `label`). Building this table
# against the old ambiguous `label` column would have made it impossible
# to tell whether a "label" value was the model's prediction or the
# dataset's ground truth -- exactly the research-integrity risk the
# rename fixes.
#
# Serves thesis hypothesis H1 (F1 >= 0.95 vs cloud-only baseline,
# evaluated per mode) and RQ3 (accuracy / latency / resource trade-off).

# COMMAND ----------

import dlt
from pyspark.sql import functions as F

# ---------------------------------------------------
# GOLD TABLE: detection_performance
# ---------------------------------------------------
@dlt.table(
    name="industrial_ai.gold.detection_performance",
    comment=(
        "Precision/recall/F1 and inference-latency percentiles for the "
        "edge model, sliced by operational mode and model_version. "
        "Ground truth is the dataset fault label (ground_truth_label), "
        "not the model's own prediction. Serves H1 and RQ3."
    ),
    table_properties={"quality": "gold"},
)
def detection_performance():
    df = (
        dlt.read("industrial_ai.silver.silver_bearing_inference_results")
        .withColumn(
            "is_actual_anomaly", F.col("ground_truth_label") != F.lit("normal")
        )
        .withColumn(
            "outcome",
            F.when(F.col("anomaly") & F.col("is_actual_anomaly"), F.lit("TP"))
            .when(F.col("anomaly") & ~F.col("is_actual_anomaly"), F.lit("FP"))
            .when(~F.col("anomaly") & F.col("is_actual_anomaly"), F.lit("FN"))
            .otherwise(F.lit("TN")),
        )
    )

    grouped = df.groupBy(
        "mode", F.coalesce(F.col("model_version"), F.lit("unversioned")).alias("model_version")
    ).agg(
        F.count("*").alias("n_events"),
        F.sum(F.when(F.col("outcome") == "TP", 1).otherwise(0)).alias("tp"),
        F.sum(F.when(F.col("outcome") == "FP", 1).otherwise(0)).alias("fp"),
        F.sum(F.when(F.col("outcome") == "FN", 1).otherwise(0)).alias("fn"),
        F.sum(F.when(F.col("outcome") == "TN", 1).otherwise(0)).alias("tn"),
        F.expr("percentile_approx(infer_ms, 0.5)").alias("infer_ms_p50"),
        F.expr("percentile_approx(infer_ms, 0.99)").alias("infer_ms_p99"),
    )

    return grouped.withColumn(
        "precision",
        F.when(F.col("tp") + F.col("fp") > 0, F.col("tp") / (F.col("tp") + F.col("fp"))),
    ).withColumn(
        "recall",
        F.when(F.col("tp") + F.col("fn") > 0, F.col("tp") / (F.col("tp") + F.col("fn"))),
    ).withColumn(
        "f1",
        F.when(
            (F.col("precision").isNotNull())
            & (F.col("recall").isNotNull())
            & (F.col("precision") + F.col("recall") > 0),
            2 * F.col("precision") * F.col("recall") / (F.col("precision") + F.col("recall")),
        ),
    )
