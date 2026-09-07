# Databricks notebook source
# asset_health_summary.py — Gold Layer (DLT): Aggregated KPI Metrics
#
# Reads from the standardized Silver DLT table (`cleaned_telemetry_events`)
# and produces domain-agnostic, per-asset-type/per-device daily health
# summaries (event volume, priority mix, event recency).
#
# BUGFIX (found during consistency audit): this notebook previously read
# from a table named "telemetry_events", which does not exist anywhere in
# this pipeline (Bronze produces "raw_telemetry_events", Silver produces
# "cleaned_telemetry_events") and grouped/aggregated by camelCase columns
# ("vehicleId", "speedKmh", "engineTemperatureC", ...) that exist neither
# in the envelope schema nor as top-level Silver columns — those fields
# live inside `payload` and are only vehicle-specific. Both issues meant
# this table could never resolve inside the DLT dependency graph and
# silently hardcoded a single asset type, contradicting the domain-agnostic
# architecture. This has been corrected to consume the real, standardized
# Silver table and stay asset-type agnostic.
#
# Per-asset-type KPI aggregations (e.g. avg vehicle speed) belong in a
# downstream Gold table built on top of the config-driven flattened Silver
# tables produced by dlt/silver/flatten_payloads.py (e.g.
# silver_vehicle_telemetry), not in this domain-agnostic summary.

# COMMAND ----------

import dlt
from pyspark.sql.functions import col, count, date_trunc, max as spark_max, sum as spark_sum, when

# ---------------------------------------------------
# GOLD TABLE: asset_health_summary
#
# BUGFIX: fully-qualified with industrial_ai.gold.* so this table lands in
# the Terraform-provisioned `gold` schema regardless of the pipeline's
# `target: silver` default — see dlt/bronze/ingest_raw_events.py for the
# full explanation. Upstream read updated to the Silver table's own
# fully-qualified name (industrial_ai.silver.cleaned_telemetry_events).
# ---------------------------------------------------
@dlt.table(
    name="industrial_ai.gold.asset_health_summary",
    comment=(
        "Domain-agnostic daily asset health summary (event volume, "
        "priority mix, last-seen) aggregated from standardized Silver "
        "telemetry events. Works for any asset_type without modification."
    ),
    table_properties={"quality": "gold"},
)
def asset_health_summary():
    return (
        dlt.read("industrial_ai.silver.cleaned_telemetry_events")
        .withColumn("event_date", date_trunc("day", col("timestamp")))
        .groupBy("asset_type", "device_id", "event_date")
        .agg(
            count("event_id").alias("total_events"),
            spark_max("timestamp").alias("last_seen_at"),
            spark_sum(when(col("priority") == "critical", 1).otherwise(0)).alias(
                "critical_event_count"
            ),
            spark_sum(when(col("priority") == "high", 1).otherwise(0)).alias(
                "high_priority_event_count"
            ),
        )
    )
