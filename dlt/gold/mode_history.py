# Databricks notebook source
# mode_history.py — Gold Layer (DLT): Orchestrator Mode Transition History
#
# Reads the standardized Silver orchestrator_mode table (config-driven,
# see config/asset_types/orchestrator_mode.yml) and the Silver
# context_snapshot table, and produces one row per mode transition with:
#   - time spent in the PREVIOUS mode before this transition fired
#     (via LEAD, partitioned per device, ordered by timestamp)
#   - the mode-switch latency: elapsed time between the most recent
#     context breach sample (is_breach_sample=true) for the same device
#     and the transition itself. This is the "mode switch latency < 5s"
#     thesis evidence (Sprint Report v3 §2.2), computed independently
#     from the local JSONL logs -- a genuine second, cross-checkable
#     source for the same claim.
#   - a trigger breakdown (network | cpu | confidence | severity |
#     recovery), which is the direct evidence that mode switching is
#     context-driven rather than fixed at design time (research gap
#     claims C1/C2).
#
# This is the single highest-value Gold table for the thesis: your own
# architecture doc calls mode history "the primary evidence for the
# thesis evaluation."

# COMMAND ----------

import dlt
from pyspark.sql import functions as F
from pyspark.sql.window import Window

# ---------------------------------------------------
# GOLD TABLE: mode_history
#
# Fully-qualified with industrial_ai.gold.* so this table lands in the
# Terraform-provisioned `gold` schema regardless of the pipeline's
# `target: bronze` default — same pattern as
# dlt/gold/asset_health_summary.py.
# ---------------------------------------------------
@dlt.table(
    name="industrial_ai.gold.mode_history",
    comment=(
        "Every orchestrator mode transition, with time-in-previous-mode, "
        "mode-switch latency (context breach -> transition), and trigger "
        "breakdown. Primary evidence table for mode-switch-latency and "
        "context-driven-orchestration thesis claims (C1/C2)."
    ),
    table_properties={"quality": "gold"},
)
def mode_history():
    modes = (
        dlt.read("industrial_ai.silver.silver_orchestrator_mode")
        .select(
            "event_id",
            "device_id",
            F.col("timestamp").alias("transition_at"),
            "from_mode",
            "to_mode",
            "trigger",
            "rtt_ms",
            "cpu_pct",
            "edge_confidence",
            "breach_count",
            "policy_version",
        )
    )

    # Time spent in the mode this transition is LEAVING, i.e. the gap
    # between the previous transition for this device and this one.
    device_window = Window.partitionBy("device_id").orderBy("transition_at")
    modes = modes.withColumn(
        "previous_transition_at", F.lag("transition_at").over(device_window)
    ).withColumn(
        "time_in_previous_mode_s",
        (
            F.col("transition_at").cast("double")
            - F.col("previous_transition_at").cast("double")
        ),
    )

    # Mode-switch latency: most recent breach-flagged context sample for
    # the same device at or before this transition's timestamp.
    breaches = (
        dlt.read("industrial_ai.silver.silver_context_snapshot")
        .filter(F.col("is_breach_sample") == True)  # noqa: E712
        .select("device_id", F.col("timestamp").alias("breach_at"))
    )

    joined = modes.join(
        breaches,
        on=(
            (modes.device_id == breaches.device_id)
            & (breaches.breach_at <= modes.transition_at)
        ),
        how="left",
    ).drop(breaches.device_id)

    latest_breach = (
        joined.groupBy(
            "event_id",
            "device_id",
            "transition_at",
            "from_mode",
            "to_mode",
            "trigger",
            "rtt_ms",
            "cpu_pct",
            "edge_confidence",
            "breach_count",
            "policy_version",
            "time_in_previous_mode_s",
        )
        .agg(F.max("breach_at").alias("latest_breach_at"))
        .withColumn(
            "mode_switch_latency_s",
            F.col("transition_at").cast("double") - F.col("latest_breach_at").cast("double"),
        )
    )

    return latest_breach
