# Databricks notebook source
# cloud_egress.py — Gold Layer (DLT): Cloud Egress Reduction
#
# Reads the standardized Silver bearing_inference table and estimates how
# much telemetry actually reached the cloud versus how much the edge
# orchestrator processed in total, per mode. Serves H3 (>= 40% cloud
# operational cost reduction vs static cloud-offload).
#
# Measurement approach: `stats_total` on each bearing_inference event is
# the orchestrator's own cumulative count of events processed so far in
# the current run (see config/asset_types/bearing_inference.yml). Events
# only reach this platform's Bronze layer at all when the orchestrator's
# Policy Executor actually transmits them -- which happens in
# CLOUD_OPTIMISED (full telemetry) and HYBRID (escalated event + raw
# context) modes, and does NOT happen in EDGE_ONLY / EDGE_AUTONOMOUS
# (offload suspended, events buffered locally per the three-tier
# retention design). So for any given run:
#   - max(stats_total) across all modes approximates total events the
#     edge orchestrator processed during the run;
#   - count(*) of rows actually landed in this table, grouped by mode,
#     is the events that were actually transmitted to the cloud.
# The ratio of (2) to (1) is a direct, evidence-based cost/egress
# reduction figure that needs no synthetic "static baseline" simulation
# -- it is measured from the same run the adaptive system produced.
#
# Cross-check: this can be compared against Azure Event Hub's own
# IncomingMessages metric for the same time window as an independent
# verification of the same number.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F

# ---------------------------------------------------
# GOLD TABLE: cloud_egress
# ---------------------------------------------------
@dlt.table(
    name="industrial_ai.gold.cloud_egress",
    comment=(
        "Events actually transmitted to the cloud per mode, versus total "
        "events processed by the edge orchestrator (stats_total). Serves "
        "H3 (cloud cost/egress reduction) with a cross-check against "
        "Azure Event Hub's own IncomingMessages metric."
    ),
    table_properties={"quality": "gold"},
)
def cloud_egress():
    df = dlt.read("industrial_ai.silver.silver_bearing_inference_results").select(
        "device_id", "mode", F.col("timestamp").alias("event_at"), "stats_total"
    )

    by_mode = df.groupBy("device_id", "mode").agg(
        F.count("*").alias("events_landed_in_cloud"),
        F.max("stats_total").alias("max_stats_total_in_mode"),
        F.min("event_at").alias("first_seen_at"),
        F.max("event_at").alias("last_seen_at"),
    )

    total_processed = df.groupBy("device_id").agg(
        F.max("stats_total").alias("total_events_processed_by_orchestrator")
    )

    return by_mode.join(total_processed, on="device_id", how="left").withColumn(
        "pct_of_processed_events_landed_in_cloud",
        F.when(
            F.col("total_events_processed_by_orchestrator") > 0,
            F.col("events_landed_in_cloud") / F.col("total_events_processed_by_orchestrator"),
        ),
    )
