# Databricks notebook source
# delta_optimize_vacuum.py — Weekly Delta maintenance
#
# P1-10: Compacts small files (OPTIMIZE + Z-ORDER) and removes stale snapshots
# (VACUUM) across Silver and Gold Delta tables.
#
# Why this matters:
#   DLT and the streaming consumer produce many small Parquet files per
#   micro-batch. Without periodic OPTIMIZE, read queries degrade as the
#   file-listing overhead grows. VACUUM reclaims storage for files that are
#   past the 7-day retention window.

from pyspark.sql import SparkSession

spark = SparkSession.builder.getOrCreate()

CATALOG = "industrial_ai"

# Tables to maintain — (schema, table, z_order_cols)
# Z-ORDER columns are chosen to align with the most common query filters.
TABLES = [
    ("silver", "cleaned_telemetry_events",       ["device_id", "timestamp"]),
    ("silver", "flattened_bearing_telemetry",     ["device_id", "timestamp"]),
    ("silver", "flattened_vehicle_telemetry",     ["device_id", "timestamp"]),
    ("silver", "flattened_orchestrator_mode",     ["device_id", "timestamp"]),
    ("silver", "flattened_context_snapshot",      ["device_id", "timestamp"]),
    ("silver", "bearing_inference_results",       ["device_id", "timestamp"]),
    ("silver", "quarantine_telemetry_events",     ["device_id"]),
    ("gold",   "asset_health_summary",            ["asset_type", "window_start"]),
    ("gold",   "bearing_ml_features",             ["device_id", "timestamp"]),
    ("gold",   "mode_history",                    ["device_id"]),
    ("gold",   "detection_performance",           ["device_id", "window_start"]),
    ("gold",   "edge_autonomy",                   ["window_start"]),
    ("gold",   "cloud_egress",                    ["window_start"]),
    ("gold",   "escalation_efficacy",             ["window_start"]),
]

VACUUM_RETAIN_HOURS = 168  # 7 days — matches Event Hub retention (P1-14)

errors = []
for schema, table, z_cols in TABLES:
    fqn = f"`{CATALOG}`.`{schema}`.`{table}`"
    try:
        z_order_clause = ", ".join(z_cols)
        print(f"OPTIMIZE {fqn} ZORDER BY ({z_order_clause})")
        spark.sql(f"OPTIMIZE {fqn} ZORDER BY ({z_order_clause})")

        print(f"VACUUM {fqn} RETAIN {VACUUM_RETAIN_HOURS} HOURS")
        spark.sql(f"VACUUM {fqn} RETAIN {VACUUM_RETAIN_HOURS} HOURS")

        print(f"  ✓ {fqn}")
    except Exception as e:
        msg = f"FAILED {fqn}: {e}"
        print(msg)
        errors.append(msg)

if errors:
    raise RuntimeError(
        f"Delta maintenance failed for {len(errors)} table(s):\n" + "\n".join(errors)
    )

print("Delta maintenance complete.")
