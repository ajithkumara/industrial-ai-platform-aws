# Databricks notebook source
# edge_autonomy.py — Gold Layer (DLT): Edge Autonomy During Outages
#
# Reads the standardized Silver bearing_inference table and measures
# detection continuity while the orchestrator reports EDGE_AUTONOMOUS
# mode (cloud unreachable) -- the single strongest candidate result in
# the thesis, per the architecture review: "can the system continue
# detecting anomalies when the cloud disappears?"
#
# Continuity is measured as the largest gap between consecutive edge
# inference timestamps for a device WHILE that device is in
# EDGE_AUTONOMOUS mode. A large gap indicates the edge model stopped
# producing decisions during the outage (a continuity failure); a small,
# stable gap close to the sensor's normal sampling interval indicates
# uninterrupted local detection -- the direct evidence for H2 (100%
# inference continuity during outages of any duration).
#
# Serves thesis hypothesis H2 and research gap claim C3.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F
from pyspark.sql.window import Window

# ---------------------------------------------------
# GOLD TABLE: edge_autonomy
# ---------------------------------------------------
@dlt.table(
    name="industrial_ai.gold.edge_autonomy",
    comment=(
        "Detection continuity evidence during EDGE_AUTONOMOUS windows: "
        "event counts and largest inter-event gap per device/outage "
        "window. Serves H2 (100% inference continuity during outages) "
        "and research gap claim C3."
    ),
    table_properties={"quality": "gold"},
)
def edge_autonomy():
    df = dlt.read("industrial_ai.silver.silver_bearing_inference_results").select(
        "device_id", "mode", F.col("timestamp").alias("event_at"), "anomaly"
    )

    device_window = Window.partitionBy("device_id").orderBy("event_at")

    with_gaps = df.withColumn(
        "previous_event_at", F.lag("event_at").over(device_window)
    ).withColumn(
        "gap_s",
        F.col("event_at").cast("double") - F.col("previous_event_at").cast("double"),
    )

    # An "outage window" boundary is any transition into or out of
    # EDGE_AUTONOMOUS for a device -- group consecutive same-mode rows
    # into windows via a running count of mode changes (standard
    # gaps-and-islands pattern).
    is_new_window = (
        F.col("mode")
        != F.lag("mode").over(device_window)
    ) | F.lag("mode").over(device_window).isNull()
    with_window_id = with_gaps.withColumn(
        "window_id", F.sum(F.when(is_new_window, 1).otherwise(0)).over(device_window)
    )

    autonomous_windows = with_window_id.filter(F.col("mode") == "EDGE_AUTONOMOUS")

    return autonomous_windows.groupBy("device_id", "window_id").agg(
        F.min("event_at").alias("window_started_at"),
        F.max("event_at").alias("window_ended_at"),
        F.count("*").alias("n_events_during_outage"),
        F.sum(F.when(F.col("anomaly"), 1).otherwise(0)).alias("n_anomalies_during_outage"),
        F.max("gap_s").alias("largest_inter_event_gap_s"),
        F.avg("gap_s").alias("avg_inter_event_gap_s"),
    ).withColumn(
        "outage_duration_s",
        F.col("window_ended_at").cast("double") - F.col("window_started_at").cast("double"),
    )
