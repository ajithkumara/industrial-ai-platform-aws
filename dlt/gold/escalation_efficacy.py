# Databricks notebook source
# escalation_efficacy.py — Gold Layer (DLT): Edge/Cloud Escalation Efficacy
#
# Joins the standardized Silver bearing_inference table (the edge
# verdict) with the Silver cloud_validation table (CloudForest's
# asynchronous second opinion, see config/asset_types/cloud_validation.yml)
# on the escalation correlation key (cloud_validation.source_event_id =
# bearing_inference.event_id), and measures agreement rate and
# accuracy-vs-ground-truth for both the edge and cloud verdicts, sliced
# by edge confidence bucket and mode.
#
# This is the novel result table: research gap claim C4 --
# "does escalating uncertain events to a heavier cloud model improve
# confidence, and does the orchestrator escalate in the right cases?"
# It answers, scientifically: when the edge model is uncertain, does
# cloud ML provide useful additional information?
#
# Architectural note: CloudForest is one possible implementation of the
# HYBRID-mode cloud validation function, not the definition of it (see
# config/asset_types/cloud_validation.yml). This table is written purely
# against the event contract (edge_confidence, cloud_score,
# agrees_with_edge, ...), so swapping the underlying cloud model
# implementation requires no change here.
#
# The edge decision is never blocked or overridden by cloud_validation --
# this table is enrichment/analysis over decisions the edge already made
# and acted on.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F

# ---------------------------------------------------
# GOLD TABLE: escalation_efficacy
# ---------------------------------------------------
@dlt.table(
    name="industrial_ai.gold.escalation_efficacy",
    comment=(
        "Edge/cloud agreement rate and edge-vs-cloud accuracy, sliced by "
        "edge confidence bucket and mode, for HYBRID-mode escalations. "
        "Serves research gap claim C4 / RQ2 -- the novel escalation "
        "result table."
    ),
    table_properties={"quality": "gold"},
)
def escalation_efficacy():
    edge = dlt.read("industrial_ai.silver.silver_bearing_inference_results").select(
        F.col("event_id").alias("edge_event_id"),
        "mode",
        "anomaly",
        "anomaly_score",
        "edge_confidence",
        "ground_truth_label",
    )

    cloud = dlt.read("industrial_ai.silver.silver_cloud_validation_results").select(
        "source_event_id",
        "cloud_anomaly",
        "cloud_score",
        "agrees_with_edge",
        "validation_latency_ms",
    )

    joined = edge.join(
        cloud, edge.edge_event_id == cloud.source_event_id, how="inner"
    ).withColumn("is_actual_anomaly", F.col("ground_truth_label") != F.lit("normal"))

    # Confidence bucketing: low/medium/high. NULL edge_confidence (not
    # yet emitted by the real orchestrator) falls into its own bucket
    # rather than being silently dropped or miscategorized.
    bucketed = joined.withColumn(
        "edge_confidence_bucket",
        F.when(F.col("edge_confidence").isNull(), F.lit("unknown"))
        .when(F.col("edge_confidence") < 0.5, F.lit("low"))
        .when(F.col("edge_confidence") < 0.8, F.lit("medium"))
        .otherwise(F.lit("high")),
    ).withColumn(
        "edge_correct", F.col("anomaly") == F.col("is_actual_anomaly")
    ).withColumn(
        "cloud_correct", F.col("cloud_anomaly") == F.col("is_actual_anomaly")
    )

    return bucketed.groupBy("mode", "edge_confidence_bucket").agg(
        F.count("*").alias("n_escalations"),
        F.avg(F.col("agrees_with_edge").cast("double")).alias("agreement_rate"),
        F.avg(F.col("edge_correct").cast("double")).alias("edge_accuracy"),
        F.avg(F.col("cloud_correct").cast("double")).alias("cloud_accuracy"),
        F.expr("percentile_approx(validation_latency_ms, 0.5)").alias(
            "validation_latency_ms_p50"
        ),
    ).withColumn(
        "cloud_accuracy_improvement", F.col("cloud_accuracy") - F.col("edge_accuracy")
    )
