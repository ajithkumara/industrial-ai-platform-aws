# Databricks notebook source
# clean_and_deduplicate.py — Silver Layer (DLT): Cleansing & Transformation
#
# Reads from the Bronze DLT table, applies envelope validation,
# deduplicates by event_id, and normalizes timestamps.
# Domain-agnostic.

import dlt
from pyspark.sql.functions import col, to_timestamp, row_number
from pyspark.sql.window import Window

# ---------------------------------------------------
# SILVER TABLE: cleaned_telemetry_events
#
# Fully-qualified with industrial_ai.silver.* so this table lands in the
# Terraform-provisioned `silver` schema regardless of the pipeline's
# `target: bronze` default. Upstream read uses the bronze table's short
# name ("telemetry_bronze", as registered in
# dlt/bronze/ingest_raw_events.py) — within a single DLT pipeline,
# dlt.read() resolves other tables in that same pipeline by their
# registered name, not by fully-qualified catalog.schema.table.
# ---------------------------------------------------
@dlt.table(
    name="industrial_ai.silver.cleaned_telemetry_events",
    comment="Cleansed and deduplicated telemetry envelope from the bronze layer.",
    table_properties={"quality": "silver"},
)
# TRIM(...) <> '' in addition to IS NOT NULL: an empty (or whitespace-only)
# string satisfies IS NOT NULL, so the previous expectations admitted events
# with event_id="" into Silver. Because every such event shares that key,
# the dedup window below would collapse unrelated events into one row --
# silent data loss. Found by the DQ6 scenario in
# tests/integration/data_quality_scenarios.py. This is the second of two
# defences; the first is min_length=1 on shared/telemetry_event.py, which
# rejects these at the consumer before they ever reach Bronze. Both are kept
# so that anything reaching Bronze by another path (backfill, replay, direct
# write) is still caught here.
@dlt.expect_or_drop("valid_event_id",   "event_id IS NOT NULL AND TRIM(event_id) <> ''")
@dlt.expect_or_drop("valid_device_id",  "device_id IS NOT NULL AND TRIM(device_id) <> ''")
@dlt.expect_or_drop("valid_asset_type", "asset_type IS NOT NULL AND TRIM(asset_type) <> ''")
@dlt.expect_or_drop("valid_timestamp",  "timestamp IS NOT NULL")
def cleaned_telemetry_events():
    df = (
        dlt.read("telemetry_bronze")
        .select(
            col("event_id"),
            col("device_id"),
            col("asset_type"),
            col("schema_version"),
            col("priority"),
            col("payload"),
            to_timestamp(col("timestamp")).alias("timestamp"),
            col("_source_file"),
            col("_ingested_at")
        )
    )

    # Deduplicate by event_id, keeping the most recent _ingested_at
    window_spec = Window.partitionBy("event_id").orderBy(col("_ingested_at").desc())
    deduped_df = df.withColumn("rn", row_number().over(window_spec)).filter(col("rn") == 1).drop("rn")

    return deduped_df


# ---------------------------------------------------
# SILVER QUARANTINE TABLE: quarantine_telemetry_events
#
# P1-11: Captures every Bronze event that FAILS at least one of the
# Silver DQ expectations above, so that rejected events are traceable
# rather than silently dropped.
#
# This mirrors the complement of the @dlt.expect_or_drop predicates on
# cleaned_telemetry_events. Any event that would be dropped from the
# main Silver table lands here for investigation and potential replay.
#
# Downstream consumers MUST NOT read from this table for production
# aggregations — it exists for data quality auditing only.
# ---------------------------------------------------
@dlt.table(
    name="industrial_ai.silver.quarantine_telemetry_events",
    comment="P1-11: Bronze events that failed Silver DQ expectations. For audit and replay only.",
    table_properties={
        "quality": "quarantine",
        "pipelines.reset.allowed": "true",
    },
)
def quarantine_telemetry_events():
    """
    Reads raw Bronze events and keeps only those that FAIL at least one
    Silver expectation — i.e. the exact set that cleaned_telemetry_events drops.

    Adds a `_quarantine_reason` column listing which expectations failed,
    so operators can triage at a glance.
    """
    from pyspark.sql.functions import array, array_remove, lit, when

    df = dlt.read("telemetry_bronze")

    # Replicate each @dlt.expect_or_drop predicate as an inverse flag.
    # A row is quarantined if ANY flag is True.
    df = df.withColumn(
        "_fail_event_id",
        ~(col("event_id").isNotNull() & (col("event_id") != ""))
    ).withColumn(
        "_fail_device_id",
        ~(col("device_id").isNotNull() & (col("device_id") != ""))
    ).withColumn(
        "_fail_asset_type",
        ~(col("asset_type").isNotNull() & (col("asset_type") != ""))
    ).withColumn(
        "_fail_timestamp",
        col("timestamp").isNull()
    )

    quarantined = df.filter(
        col("_fail_event_id") |
        col("_fail_device_id") |
        col("_fail_asset_type") |
        col("_fail_timestamp")
    )

    # Build a human-readable reason string.
    quarantined = quarantined.withColumn(
        "_quarantine_reason",
        array_remove(
            array(
                when(col("_fail_event_id"),   lit("invalid_event_id")).otherwise(lit(None)),
                when(col("_fail_device_id"),  lit("invalid_device_id")).otherwise(lit(None)),
                when(col("_fail_asset_type"), lit("invalid_asset_type")).otherwise(lit(None)),
                when(col("_fail_timestamp"),  lit("null_timestamp")).otherwise(lit(None)),
            ),
            None
        )
    )

    return quarantined.drop("_fail_event_id", "_fail_device_id", "_fail_asset_type", "_fail_timestamp")
