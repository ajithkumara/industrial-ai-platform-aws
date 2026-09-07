# Databricks notebook source
# bearing_ml_features.py — Gold Layer (DLT): Leakage-Safe ML Feature Dataset
#
# The canonical training/evaluation dataset for bearing anomaly detection.
# Grain: ONE ROW PER SENSOR WINDOW, keyed by event_id.
#
# Implements the normative specification in ml/feature_spec.py. That module
# is pure Python and is what the offline tests verify; the constants below
# are asserted against it by tests/test_feature_spec.py, so the two cannot
# silently diverge. Read feature_spec.py first -- it explains WHY each rule
# exists, and those reasons are the defensibility of every metric in the
# evaluation chapter.
#
# THREE PROPERTIES THIS TABLE GUARANTEES
#
#   1. NO LEAKAGE. Orchestration and model-outcome columns (mode, rtt_ms,
#      cpu_pct, cloud_reachable, edge_confidence, anomaly, anomaly_score,
#      and every cloud_validation field) are ABSENT by construction. Those
#      are what the research evaluates; training on them would be circular.
#      Evaluation joins them from the evidence tables at analysis time,
#      where unrestricted joins are correct. The invariant is: no outcome or
#      context leakage into TRAINING features; unrestricted joins allowed in
#      post-hoc EVALUATION datasets.
#
#   2. NO SILENT NULLS. A row missing any required feature is QUARANTINED
#      into industrial_ai.gold.bearing_ml_features_quarantine with a stated
#      reason, not imputed and not NULL-filled. The DQ9/DQ10 data-quality
#      scenarios demonstrated that a missing payload field and an
#      uncastable one both surface as NULL and are indistinguishable
#      downstream -- so trusting Silver's NULLs would put unrecoverable
#      ambiguity into the training set.
#
#   3. NO TEMPORAL OR RECORDING LEAKAGE. Splits are assigned at RECORDING
#      level (source_file), stratified by class; trend features look strictly
#      backward within a recording. Windows cut from one recording are
#      near-duplicates of their neighbours, so a random window-level split
#      would place near-identical samples in both train and test and inflate
#      every reported metric. This is the most common methodological failure
#      in bearing-fault ML literature.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F
from pyspark.sql.window import Window

# --- mirrored from ml/feature_spec.py (asserted equal by tests) ------------
TIME_DOMAIN_FEATURES = [
    "rms", "peak", "crest", "kurtosis", "skew", "variance", "mean_abs",
]
REQUIRED_NON_NULL = TIME_DOMAIN_FEATURES + [
    "event_id", "source_file", "ground_truth_label", "window_idx",
]
TREND_WINDOW_ROWS = 5
NORMAL_LABEL = "normal"
NORMAL_TRAIN_RATIO = 0.6
NORMAL_VALIDATION_RATIO = 0.2
FAULT_VALIDATION_RATIO = 0.5
FEATURE_SET_VERSION = "bearing-features-v1"
# ---------------------------------------------------------------------------

_SOURCE = "industrial_ai.silver.silver_bearing_sensor_telemetry"


def _with_validity(df):
    """Attach a quarantine reason listing every column that is NULL."""
    missing = F.concat_ws(
        ",",
        *[
            F.when(F.col(c).isNull(), F.lit(c)).otherwise(F.lit(None))
            for c in REQUIRED_NON_NULL
        ],
    )
    return df.withColumn(
        "missing_columns", F.when(missing == "", F.lit(None)).otherwise(missing)
    ).withColumn("is_valid", F.col("missing_columns").isNull())


# ---------------------------------------------------------------------
# GOLD TABLE: bearing_ml_features
# ---------------------------------------------------------------------
@dlt.table(
    name="industrial_ai.gold.bearing_ml_features",
    comment=(
        "Leakage-safe ML feature dataset for bearing anomaly detection. One "
        "row per sensor window. Time-domain and backward-looking trend "
        "features only; orchestration/outcome context deliberately excluded. "
        "Recording-level stratified split. Invalid rows are quarantined, not "
        "NULL-filled. Implements ml/feature_spec.py."
    ),
    table_properties={"quality": "gold"},
)
@dlt.expect_or_fail("no_null_features", " AND ".join(f"{c} IS NOT NULL" for c in TIME_DOMAIN_FEATURES))
@dlt.expect_or_fail("split_assigned", "dataset_split IN ('TRAIN','VALIDATION','TEST')")
def bearing_ml_features():
    base = _with_validity(dlt.read(_SOURCE)).filter(F.col("is_valid"))

    # -- Recording-level stratified split -------------------------------
    # Assign at the level of DISTINCT (source_file, ground_truth_label),
    # then broadcast back to every window of that recording, so a recording
    # can never straddle two splits.
    recordings = base.select("source_file", "ground_truth_label").distinct()

    label_window = Window.partitionBy("ground_truth_label").orderBy("source_file")
    label_total = Window.partitionBy("ground_truth_label")

    recordings = (
        recordings
        .withColumn("rank", F.row_number().over(label_window))
        .withColumn("total", F.count("*").over(label_total))
        # position in [0,1) within the label group; deterministic because
        # the ordering is by source_file, not by anything run-dependent.
        .withColumn("position", (F.col("rank") - 1) / F.col("total"))
        .withColumn(
            "dataset_split",
            F.when(
                F.col("ground_truth_label") == F.lit(NORMAL_LABEL),
                # Small-N guarantee, mirrors ml/feature_spec.py::assign_split.
                # CWRU's Normal Baseline has exactly 4 recordings and no more
                # exist to download; the ratio formula below silently
                # produces zero TEST recordings at total=4, making true
                # negatives/false positives unmeasurable in the final
                # evaluation. Below total=5, assign explicitly instead.
                F.when(F.col("total") == F.lit(1), F.lit("TRAIN"))
                .when(
                    F.col("total") == F.lit(2),
                    F.when(F.col("rank") == F.lit(1), F.lit("TRAIN")).otherwise(F.lit("VALIDATION")),
                )
                .when(
                    F.col("total") <= F.lit(4),
                    F.when(F.col("rank") <= F.col("total") - F.lit(2), F.lit("TRAIN"))
                    .when(F.col("rank") == F.col("total") - F.lit(1), F.lit("VALIDATION"))
                    .otherwise(F.lit("TEST")),
                )
                .when(F.col("position") < F.lit(NORMAL_TRAIN_RATIO), F.lit("TRAIN"))
                .when(
                    F.col("position") < F.lit(NORMAL_TRAIN_RATIO + NORMAL_VALIDATION_RATIO),
                    F.lit("VALIDATION"),
                )
                .otherwise(F.lit("TEST")),
            ).otherwise(
                # Fault recordings never enter TRAIN: Isolation Forest is
                # fitted on normal data only.
                F.when(F.col("position") < F.lit(FAULT_VALIDATION_RATIO), F.lit("VALIDATION"))
                .otherwise(F.lit("TEST"))
            ),
        )
        .select("source_file", "ground_truth_label", "dataset_split")
    )

    df = base.join(recordings, on=["source_file", "ground_truth_label"], how="inner")

    # -- Backward-looking trend features --------------------------------
    # rowsBetween(-(N-1), 0) spans the current row and the N-1 preceding
    # rows ONLY. Including the current row is correct -- its own value is
    # available at inference time. Including any FOLLOWING row would leak
    # the future and is what makes naive rolling features invalid.
    trend_window = (
        Window.partitionBy("source_file")
        .orderBy("window_idx")
        .rowsBetween(-(TREND_WINDOW_ROWS - 1), 0)
    )
    order_window = Window.partitionBy("source_file").orderBy("window_idx")

    df = (
        df
        .withColumn("rms_roll_mean_5", F.avg("rms").over(trend_window))
        .withColumn("rms_roll_std_5", F.coalesce(F.stddev("rms").over(trend_window), F.lit(0.0)))
        .withColumn("kurtosis_roll_mean_5", F.avg("kurtosis").over(trend_window))
        .withColumn("rms_delta_1", F.col("rms") - F.lag("rms", 1).over(order_window))
        .withColumn("window_position", F.row_number().over(order_window))
        # The first TREND_WINDOW_ROWS-1 rows of a recording have an
        # incomplete lookback. They are retained (dropping them would bias
        # the dataset toward later windows) but flagged, so an experiment
        # can exclude them without recomputing the table.
        .withColumn(
            "trend_window_complete",
            F.col("window_position") >= F.lit(TREND_WINDOW_ROWS),
        )
        # rms_delta_1 is undefined for the first row of each recording;
        # 0.0 is the correct neutral value for "no change observed yet"
        # and keeps the column NOT NULL.
        .withColumn("rms_delta_1", F.coalesce(F.col("rms_delta_1"), F.lit(0.0)))
    )

    return df.select(
        # -- identity / grouping --
        "event_id",
        "device_id",
        "timestamp",
        "source_file",
        "seq",
        "window_idx",
        "window_position",
        "sampling_rate_hz",
        # NULL for synthetic acceptance-test data (which never sets it);
        # populated for every real-data loader run. Filter on this column
        # to isolate one experiment's data from synthetic and from any
        # other real-data run -- see config/asset_types/bearing_sensor.yml.
        "dataset_run_id",
        # -- split metadata --
        "dataset_split",
        F.col("trend_window_complete"),
        # -- evaluation only: NEVER a model input --
        "ground_truth_label",
        (F.col("ground_truth_label") != F.lit(NORMAL_LABEL)).alias("is_actual_anomaly"),
        # Encodes the unsupervised contract directly in the data: fitting
        # code filters on this single column rather than reimplementing
        # "TRAIN and normal" and risking getting it wrong.
        (
            (F.col("dataset_split") == F.lit("TRAIN"))
            & (F.col("ground_truth_label") == F.lit(NORMAL_LABEL))
        ).alias("is_training_eligible"),
        # -- feature group: time_domain --
        *TIME_DOMAIN_FEATURES,
        # -- feature group: trend (backward-looking) --
        "rms_roll_mean_5",
        "rms_roll_std_5",
        "rms_delta_1",
        "kurtosis_roll_mean_5",
        # -- provenance --
        F.lit(FEATURE_SET_VERSION).alias("feature_set_version"),
        F.current_timestamp().alias("generated_at"),
    )


# ---------------------------------------------------------------------
# GOLD TABLE: bearing_ml_features_quarantine
# ---------------------------------------------------------------------
@dlt.table(
    name="industrial_ai.gold.bearing_ml_features_quarantine",
    comment=(
        "Rows rejected from bearing_ml_features because a required feature "
        "or identity column was NULL, with the offending columns named. "
        "Quarantining rather than imputing keeps unrecoverable ambiguity "
        "out of the training set; this table is the audit trail and should "
        "be checked before every training run."
    ),
    table_properties={"quality": "gold"},
)
def bearing_ml_features_quarantine():
    return (
        _with_validity(dlt.read(_SOURCE))
        .filter(~F.col("is_valid"))
        .select(
            "event_id",
            "device_id",
            "timestamp",
            "source_file",
            "seq",
            "window_idx",
            "dataset_run_id",
            "ground_truth_label",
            F.col("missing_columns").alias("quarantine_missing_columns"),
            F.lit("required column NULL").alias("quarantine_reason"),
            F.lit(FEATURE_SET_VERSION).alias("feature_set_version"),
            F.current_timestamp().alias("quarantined_at"),
        )
    )
