"""
Local PySpark reproduction of the Silver + Gold logical contract, run on a real
SparkSession against synthetic acceptance data.

WHY THIS EXISTS
---------------
The DLT notebooks (dlt/silver/clean_and_deduplicate.py, dlt/silver/flatten_payloads.py,
dlt/gold/asset_health_summary.py) are byte-identical to the Azure reference
(verified in docs/evidence/terraform-evidence + M7 parity check) and only run
inside a Databricks DLT pipeline. This test reproduces their EXACT transformation
logic on a local Spark engine — reading synthetic events as JSON (mirroring the
Bronze Auto Loader's schema inference), applying the same Silver expectations +
dedup, and the same config-driven flatten using the REAL config/asset_types/*.yml
and dlt/common/helpers.py — so the ACCEPTANCE_CONTRACT logical outcomes are
verified without a live Databricks cluster.

It asserts the Azure acceptance values UNCHANGED (never weakened):
  DQ2  duplicate            -> Bronze 2, Silver 1   (dedup by event_id)
  DQ7  unparseable timestamp-> dropped at Silver
  DQ8  unknown asset_type   -> retained in cleaned, no flattened row
  DQ9  missing payload field-> flattened row present, that column NULL
  DQ10 wrong payload type    -> flattened row present, that column NULL
"""

from __future__ import annotations

import json
import os

import pytest

pyspark = pytest.importorskip("pyspark")
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import StructType

from dlt.common.helpers import load_asset_type_config

_ASSET_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config", "asset_types")


@pytest.fixture(scope="module")
def spark():
    # Sandbox has no resolvable hostname; pin Spark to loopback.
    os.environ.setdefault("SPARK_LOCAL_IP", "127.0.0.1")
    os.environ.setdefault(
        "JAVA_HOME",
        os.path.dirname(os.path.dirname(os.path.realpath("/usr/bin/java"))),
    )
    s = (
        SparkSession.builder.master("local[1]")
        .config("spark.driver.host", "127.0.0.1")
        .config("spark.driver.bindAddress", "127.0.0.1")
        .appName("silver-gold-parity")
        .config("spark.sql.shuffle.partitions", "1")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )
    yield s
    s.stop()


def _bronze_from_events(spark, events, tmp_path):
    """Write events as JSONL and read with schema inference — mirrors the Bronze
    Auto Loader (cloudFiles json inferColumnTypes) + the _ingested_at column."""
    p = tmp_path / "bronze.jsonl"
    p.write_text("\n".join(json.dumps(e) for e in events))
    df = spark.read.json(str(p))
    # Bronze adds _source_file / _ingested_at (here: deterministic per row order).
    return df.withColumn("_source_file", F.lit(str(p))) \
             .withColumn("_ingested_at", F.monotonically_increasing_id().cast("long"))


def _silver_clean_dedup(bronze):
    """Reproduces dlt/silver/clean_and_deduplicate.py exactly."""
    from pyspark.sql.window import Window
    df = bronze.select(
        F.col("event_id"), F.col("device_id"), F.col("asset_type"),
        F.col("schema_version"), F.col("priority"), F.col("payload"),
        F.to_timestamp(F.col("timestamp")).alias("timestamp"),
        F.col("_source_file"), F.col("_ingested_at"),
    )
    # @dlt.expect_or_drop on the 4 identity fields (with TRIM<>'').
    df = df.filter(
        F.col("event_id").isNotNull() & (F.trim(F.col("event_id")) != "") &
        F.col("device_id").isNotNull() & (F.trim(F.col("device_id")) != "") &
        F.col("asset_type").isNotNull() & (F.trim(F.col("asset_type")) != "") &
        F.col("timestamp").isNotNull()
    )
    w = Window.partitionBy("event_id").orderBy(F.col("_ingested_at").desc())
    return df.withColumn("rn", F.row_number().over(w)).filter(F.col("rn") == 1).drop("rn")


def _source_path_exists(schema: StructType, dotted: str) -> bool:
    fields = schema.fields
    parts = dotted.split(".")
    for i, part in enumerate(parts):
        m = next((f for f in fields if f.name == part), None)
        if m is None:
            return False
        if i < len(parts) - 1:
            if not isinstance(m.dataType, StructType):
                return False
            fields = m.dataType.fields
    return True


def _flatten(cleaned, config):
    """Reproduces dlt/silver/flatten_payloads.py's per-asset flatten + null fallback."""
    envelope = ["event_id", "device_id", "asset_type", "timestamp", "priority", "schema_version"]
    df = cleaned.filter(F.col("asset_type") == config.asset_type)
    cols = [F.col(c) for c in envelope]
    for fm in config.fields:
        cast = fm.spark_cast_type()
        if _source_path_exists(df.schema, fm.source):
            cols.append(F.col(fm.source).cast(cast).alias(fm.target))
        else:
            cols.append(F.lit(None).cast(cast).alias(fm.target))
    return df.select(*cols)


def _evt(eid, asset="vehicle", device="CAR-1", ts="2026-08-12T12:00:00Z", payload=None):
    return {
        "event_id": eid, "device_id": device, "asset_type": asset,
        "timestamp": ts, "priority": "normal", "schema_version": "1.0.0",
        "payload": payload or {},
    }


def test_dq2_duplicate_bronze2_silver1(spark, tmp_path):
    dup = _evt("dup-1", payload={"vehicle_id": "CAR-1", "speed_kmh": 40})
    bronze = _bronze_from_events(spark, [dup, dict(dup)], tmp_path)  # same event twice
    assert bronze.count() == 2  # Bronze immutability: both retained
    silver = _silver_clean_dedup(bronze)
    assert silver.count() == 1  # dedup by event_id


def test_dq7_unparseable_timestamp_dropped_at_silver(spark, tmp_path):
    good = _evt("ok-1", payload={"vehicle_id": "CAR-1", "speed_kmh": 40})
    bad = _evt("bad-ts", ts="not-a-timestamp", payload={"vehicle_id": "CAR-2", "speed_kmh": 1})
    bronze = _bronze_from_events(spark, [good, bad], tmp_path)
    silver = _silver_clean_dedup(bronze)
    ids = {r["event_id"] for r in silver.collect()}
    assert ids == {"ok-1"}  # bad timestamp -> to_timestamp NULL -> dropped


def test_dq8_unknown_asset_retained_but_not_flattened(spark, tmp_path):
    veh = _evt("v-1", asset="vehicle", payload={"vehicle_id": "CAR-1", "speed_kmh": 40})
    unknown = _evt("u-1", asset="mystery_sensor", payload={"x": 1})
    bronze = _bronze_from_events(spark, [veh, unknown], tmp_path)
    silver = _silver_clean_dedup(bronze)
    assert silver.count() == 2  # unknown asset retained in cleaned Silver
    # flatten for vehicle yields only the vehicle row; mystery_sensor has no config
    cfg = load_asset_type_config("vehicle", asset_types_dir=_ASSET_DIR)
    flat = _flatten(silver, cfg)
    assert {r["event_id"] for r in flat.collect()} == {"v-1"}


def test_dq9_missing_payload_field_becomes_null_column(spark, tmp_path):
    # bearing_sensor config maps payload.features.rms -> rms. Omit features.rms.
    e = _evt("b-1", asset="bearing_sensor", device="bearing.DE",
             payload={"seq": 1, "label": "normal", "window_idx": 1,
                      "features": {"peak": 0.1, "crest": 2.0, "kurtosis": 1.0,
                                   "skew": 0.0, "variance": 0.01, "mean_abs": 0.05}})
    bronze = _bronze_from_events(spark, [e], tmp_path)
    silver = _silver_clean_dedup(bronze)
    cfg = load_asset_type_config("bearing_sensor", asset_types_dir=_ASSET_DIR)
    flat = _flatten(silver, cfg)
    row = flat.collect()[0]
    assert row["event_id"] == "b-1"
    assert row["rms"] is None       # missing payload.features.rms -> NULL column
    assert row["peak"] is not None  # present field still populated


def test_dq10_wrong_payload_type_becomes_null_column(spark, tmp_path):
    # kurtosis declared double; supply a non-numeric string -> cast yields NULL.
    e = _evt("b-2", asset="bearing_sensor", device="bearing.DE",
             payload={"seq": 1, "label": "normal", "window_idx": 1,
                      "features": {"rms": 0.03, "peak": 0.1, "crest": 2.0,
                                   "kurtosis": "not-a-number", "skew": 0.0,
                                   "variance": 0.01, "mean_abs": 0.05}})
    bronze = _bronze_from_events(spark, [e], tmp_path)
    silver = _silver_clean_dedup(bronze)
    cfg = load_asset_type_config("bearing_sensor", asset_types_dir=_ASSET_DIR)
    flat = _flatten(silver, cfg)
    row = flat.collect()[0]
    assert row["kurtosis"] is None  # uncastable -> NULL (not an error)
    assert row["rms"] is not None


def test_gold_asset_health_summary_aggregation(spark, tmp_path):
    # Reproduces dlt/gold/asset_health_summary.py grouping/aggregation.
    events = [
        _evt("h-1", payload={"vehicle_id": "CAR-1"}),
        _evt("h-2", payload={"vehicle_id": "CAR-1"}),
        {**_evt("h-3", payload={"vehicle_id": "CAR-1"}), "priority": "critical"},
    ]
    bronze = _bronze_from_events(spark, events, tmp_path)
    silver = _silver_clean_dedup(bronze)
    gold = (
        silver.withColumn("event_date", F.date_trunc("day", F.col("timestamp")))
        .groupBy("asset_type", "device_id", "event_date")
        .agg(
            F.count("event_id").alias("total_events"),
            F.sum(F.when(F.col("priority") == "critical", 1).otherwise(0)).alias("critical_event_count"),
        )
    )
    row = gold.collect()[0]
    assert row["total_events"] == 3
    assert row["critical_event_count"] == 1
