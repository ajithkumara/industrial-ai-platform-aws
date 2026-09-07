"""
NORMATIVE SPECIFICATION for the bearing ML feature dataset.

This module is pure Python with no Spark dependency, so it can be imported
and tested offline. `dlt/gold/bearing_ml_features.py` implements the same
rules in Spark and cites this module as the specification; the constants
below are asserted against that notebook's source by
tests/test_feature_spec.py, so the two cannot silently diverge.

Three things are specified here:

  1. FEATURE GROUPS -- which columns are legitimate model inputs, which are
     evaluation-only, and which must never enter the table at all.
  2. VALIDITY -- what makes a row usable for training/evaluation. Invalid
     rows are QUARANTINED, never silently NULL-filled.
  3. SPLIT POLICY -- recording-level, stratified, deterministic.


FEATURE GROUPS
--------------
time_domain   Legitimate model inputs. Computed at the edge on every event,
              so a model trained on them can actually run at the edge.

trend         Derived from time_domain, strictly BACKWARD-LOOKING within a
              single recording. A rolling statistic computed over a window
              that includes future rows would leak information that is not
              available at inference time and would inflate measured
              performance.

spectral      Cloud-side information advantage, derived from the raw
              waveform attached to HYBRID-escalated events. NOT part of this
              table: it exists for only a minority of events, so including
              it here would produce mostly-NULL columns and violate the
              quarantine-not-NULL principle. It belongs in a separate,
              sparser table joined on event_id.

context       Orchestration and outcome metadata (mode, rtt_ms, cpu_pct,
              cloud_reachable, edge_confidence, edge/cloud decisions).
              DELIBERATELY ABSENT from this table. These are the things the
              research is trying to evaluate; training on them would be
              circular. Evaluation joins them from the Silver/Gold evidence
              tables at analysis time, where unrestricted joins are correct.

evaluation    ground_truth_label and its derived boolean. Present, because
              evaluation needs them, but never a model input -- Isolation
              Forest is unsupervised and is fitted on unlabelled normal
              data only.


SPLIT POLICY
------------
Grouping key is `source_file` (the CWRU recording), NOT the individual
window. Windows cut from one recording are highly correlated -- adjacent
windows are near-duplicates -- so a random window-level split would place
near-identical samples in both train and test and inflate every reported
metric. This is the single most common methodological failure in
bearing-fault ML literature, and it is the first thing a knowledgeable
examiner checks.

Stratified by label so that every fault class is represented in the
evaluation splits; a naive hash could place all recordings of one class
into a single split.

Fault recordings are NEVER assigned to TRAIN. Isolation Forest is fitted on
normal data only; the fault recordings exist to measure detection, so
exposing them during fitting would both violate the unsupervised premise
and leak test information.

    normal recordings -> 60% TRAIN | 20% VALIDATION | 20% TEST
    fault  recordings ->            50% VALIDATION | 50% TEST

VALIDATION is used to select the anomaly score threshold. TEST is touched
once, at the end, to report final performance.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Feature groups
# ---------------------------------------------------------------------------

TIME_DOMAIN_FEATURES: tuple[str, ...] = (
    "rms",
    "peak",
    "crest",
    "kurtosis",
    "skew",
    "variance",
    "mean_abs",
)

# Backward-looking trend features derived from TIME_DOMAIN_FEATURES.
TREND_FEATURES: tuple[str, ...] = (
    "rms_roll_mean_5",
    "rms_roll_std_5",
    "rms_delta_1",
    "kurtosis_roll_mean_5",
)

TREND_WINDOW_ROWS = 5  # current row + 4 preceding, never any following row

# Columns that must NEVER appear in the feature table. Enforced by
# tests/test_feature_spec.py against the notebook source.
FORBIDDEN_CONTEXT_COLUMNS: tuple[str, ...] = (
    "mode",
    "rtt_ms",
    "cpu_pct",
    "cloud_reachable",
    "edge_confidence",
    "anomaly",
    "anomaly_score",
    "edge_anomaly",
    "edge_score",
    "cloud_anomaly",
    "cloud_score",
    "agrees_with_edge",
    "infer_ms",
)

EVALUATION_COLUMNS: tuple[str, ...] = (
    "ground_truth_label",
    "is_actual_anomaly",
)

# ---------------------------------------------------------------------------
# Validity — quarantine, do not NULL-fill
# ---------------------------------------------------------------------------

# A row missing any of these cannot be used and is routed to the quarantine
# table with a reason. DQ9/DQ10 demonstrated that a missing payload field and
# an uncastable one both surface as NULL and are indistinguishable
# downstream, so the feature layer must reject rather than impute.
REQUIRED_NON_NULL: tuple[str, ...] = TIME_DOMAIN_FEATURES + (
    "event_id",
    "source_file",
    "ground_truth_label",
    "window_idx",
)

# ---------------------------------------------------------------------------
# Split policy
# ---------------------------------------------------------------------------

NORMAL_LABEL = "normal"

NORMAL_TRAIN_RATIO = 0.6
NORMAL_VALIDATION_RATIO = 0.2   # TEST receives the remaining 0.2
FAULT_VALIDATION_RATIO = 0.5    # TEST receives the remaining 0.5

SPLIT_TRAIN = "TRAIN"
SPLIT_VALIDATION = "VALIDATION"
SPLIT_TEST = "TEST"

FEATURE_SET_VERSION = "bearing-features-v1"


def assign_split(label: str, rank: int, total: int) -> str:
    """
    Assign one RECORDING to a split.

    Parameters
    ----------
    label : the recording's ground-truth class
    rank  : 1-based position of this recording within its label group, in a
            deterministic ordering (the Spark implementation uses
            row_number() over (partition by label order by source_file))
    total : number of recordings in that label group

    Determinism matters: the same corpus must produce the same split on
    every run, or results are not reproducible between chapters.
    """
    if total <= 0:
        raise ValueError("total must be positive")
    if not 1 <= rank <= total:
        raise ValueError(f"rank {rank} out of bounds for total {total}")

    position = (rank - 1) / total

    if label == NORMAL_LABEL:
        # Small-N guarantee. CWRU's Normal Baseline dataset has exactly 4
        # recordings total (one per motor load) and no more exist to
        # download at this sample rate. The ratio formula below silently
        # produces ZERO TEST recordings at total=4 (position sequence
        # 0, .25, .5, .75 -> 3 TRAIN / 1 VALIDATION / 0 TEST), which would
        # make true negatives and false positives unmeasurable in the
        # final held-out evaluation -- discovered when building the real
        # CWRU dataset loader, 2026-08. Below total=5, assign explicitly
        # so every split that can be populated is populated:
        #   total=1 -> TRAIN                     (existing behaviour, unchanged)
        #   total=2 -> TRAIN, VALIDATION
        #   total=3 -> TRAIN, VALIDATION, TEST
        #   total=4 -> TRAIN, TRAIN, VALIDATION, TEST
        if total <= 4:
            if total == 1:
                return SPLIT_TRAIN
            if total == 2:
                return SPLIT_TRAIN if rank == 1 else SPLIT_VALIDATION
            if rank <= total - 2:
                return SPLIT_TRAIN
            return SPLIT_VALIDATION if rank == total - 1 else SPLIT_TEST
        if position < NORMAL_TRAIN_RATIO:
            return SPLIT_TRAIN
        if position < NORMAL_TRAIN_RATIO + NORMAL_VALIDATION_RATIO:
            return SPLIT_VALIDATION
        return SPLIT_TEST

    # Fault recordings never enter TRAIN.
    return SPLIT_VALIDATION if position < FAULT_VALIDATION_RATIO else SPLIT_TEST


def is_training_eligible(label: str, dataset_split: str) -> bool:
    """
    Isolation Forest is fitted on normal data only. Encoding this in the
    dataset removes the possibility of a training script silently fitting
    on fault windows because someone filtered on split alone.
    """
    return dataset_split == SPLIT_TRAIN and label == NORMAL_LABEL
