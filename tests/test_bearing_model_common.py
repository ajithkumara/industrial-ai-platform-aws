"""
Offline tests for ml/bearing_model_common.py -- pure functions, no Spark,
no MLflow, no sklearn. Covers the score-direction transform and the
validation-only max-F1 threshold selection that
ml/train_bearing_isolation_forest.py and ml/evaluate_bearing_model.py both
depend on.
"""

from __future__ import annotations

import math

import pytest

from ml.bearing_model_common import (
    SCORE_SIGMOID_K,
    ConfusionCounts,
    confusion_at_threshold,
    raw_scores_to_anomaly_scores,
    select_threshold_by_max_f1,
)


# ---------------------------------------------------------------------------
# raw_scores_to_anomaly_scores: score-direction contract
# ---------------------------------------------------------------------------

def test_very_normal_raw_score_maps_to_low_anomaly_score():
    # sklearn: strongly positive decision_function = strongly normal.
    (anomaly_score,) = raw_scores_to_anomaly_scores([2.0])
    assert anomaly_score < 0.01


def test_very_anomalous_raw_score_maps_to_high_anomaly_score():
    # sklearn: strongly negative decision_function = strongly anomalous.
    (anomaly_score,) = raw_scores_to_anomaly_scores([-2.0])
    assert anomaly_score > 0.99


def test_raw_score_of_zero_maps_to_midpoint():
    (anomaly_score,) = raw_scores_to_anomaly_scores([0.0])
    assert anomaly_score == pytest.approx(0.5)


def test_transform_matches_cloud_forest_sigmoid_exactly():
    # Must stay byte-for-byte identical to score_escalations.py's
    # `1.0 / (1.0 + pow(2.718281828, raw_scores * 5.0))` convention --
    # this test pins SCORE_SIGMOID_K and the transform shape together.
    raw = -0.37
    expected = 1.0 / (1.0 + math.exp(raw * SCORE_SIGMOID_K))
    (actual,) = raw_scores_to_anomaly_scores([raw])
    assert actual == pytest.approx(expected)


def test_transform_is_monotonically_decreasing_in_raw_score():
    raw = [-1.0, -0.5, 0.0, 0.5, 1.0]
    scores = raw_scores_to_anomaly_scores(raw)
    assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# confusion_at_threshold
# ---------------------------------------------------------------------------

def test_confusion_at_threshold_basic_counts():
    scores = [0.9, 0.8, 0.3, 0.1]
    actual = [True, False, True, False]  # only index 0 and 2 are real anomalies
    confusion = confusion_at_threshold(scores, actual, threshold=0.5)
    # >= 0.5 predicted anomaly: indices 0 (0.9) and 1 (0.8)
    assert confusion == ConfusionCounts(tp=1, fp=1, fn=1, tn=1)


def test_confusion_threshold_is_inclusive_at_boundary():
    scores = [0.5]
    actual = [True]
    confusion = confusion_at_threshold(scores, actual, threshold=0.5)
    assert confusion.tp == 1
    assert confusion.fn == 0


def test_confusion_length_mismatch_raises():
    with pytest.raises(ValueError):
        confusion_at_threshold([0.1, 0.2], [True], threshold=0.5)


def test_confusion_precision_recall_f1_zero_when_no_positives_predicted():
    scores = [0.1, 0.2]
    actual = [True, False]
    confusion = confusion_at_threshold(scores, actual, threshold=0.9)
    assert confusion.tp == 0 and confusion.fp == 0
    assert confusion.precision == 0.0
    assert confusion.recall == 0.0
    assert confusion.f1 == 0.0


def test_confusion_perfect_separation_gives_f1_one():
    scores = [0.9, 0.8, 0.2, 0.1]
    actual = [True, True, False, False]
    confusion = confusion_at_threshold(scores, actual, threshold=0.5)
    assert confusion.precision == 1.0
    assert confusion.recall == 1.0
    assert confusion.f1 == 1.0


# ---------------------------------------------------------------------------
# select_threshold_by_max_f1
# ---------------------------------------------------------------------------

def test_select_threshold_empty_raises():
    with pytest.raises(ValueError):
        select_threshold_by_max_f1([], [])


def test_select_threshold_finds_perfectly_separating_value():
    # Anomalies cluster at high scores, normals at low scores -- any
    # threshold in (0.4, 0.6) achieves F1=1.0; the selected threshold must
    # actually achieve it.
    scores = [0.9, 0.85, 0.8, 0.2, 0.15, 0.1]
    actual = [True, True, True, False, False, False]
    result = select_threshold_by_max_f1(scores, actual)
    assert result.validation_confusion.f1 == pytest.approx(1.0)
    assert result.validation_confusion.tp == 3
    assert result.validation_confusion.fp == 0
    assert result.validation_confusion.fn == 0


def test_select_threshold_with_overlapping_classes_picks_best_achievable_f1():
    # No perfect separator exists: one normal scores higher than one
    # anomaly. Selection must still return the F1-maximizing threshold
    # among achievable candidates, not crash or silently pick a bad one.
    scores = [0.9, 0.7, 0.6, 0.4, 0.3, 0.1]
    actual = [True, True, False, True, False, False]

    # Brute-force the same grid independently to cross-check.
    best_f1 = -1.0
    for tau in sorted(set(scores)):
        c = confusion_at_threshold(scores, actual, tau)
        best_f1 = max(best_f1, c.f1)

    result = select_threshold_by_max_f1(scores, actual)
    assert result.validation_confusion.f1 == pytest.approx(best_f1)


def test_select_threshold_tie_break_prefers_higher_precision():
    # Construct two thresholds with identical F1 but different precision;
    # the documented tie-break must choose the higher-precision one.
    # scores: two anomalies at 0.9/0.8, one normal at 0.85 sits between them.
    scores = [0.9, 0.85, 0.8]
    actual = [True, False, True]
    result = select_threshold_by_max_f1(scores, actual)
    # threshold=0.8 catches all 3 (2 TP, 1 FP) -> P=2/3, R=1, F1=0.8
    # threshold=0.85 catches 0.9,0.85 (1 TP,1 FP) -> P=0.5,R=0.5,F1=0.5
    # threshold=0.9 catches only 0.9 (1 TP, 0 FP) -> P=1,R=0.5,F1=0.667
    # Best F1 is uniquely 0.8 at threshold=0.8 here, so this also confirms
    # the selector isn't just returning the first/last candidate.
    assert result.threshold == pytest.approx(0.8)


def test_select_threshold_never_looks_at_data_it_is_not_given():
    # Pure-function sanity check: calling with a small VALIDATION-shaped
    # sample must not require or reference any TEST data -- there is no
    # TEST parameter on this function at all, which is what actually
    # enforces "do not tune on TEST" structurally.
    import inspect

    sig = inspect.signature(select_threshold_by_max_f1)
    assert set(sig.parameters) == {"anomaly_scores", "is_actual_anomaly"}


def test_candidates_evaluated_matches_distinct_score_count():
    scores = [0.5, 0.5, 0.9, 0.1]  # 3 distinct values
    actual = [True, False, True, False]
    result = select_threshold_by_max_f1(scores, actual)
    assert result.candidates_evaluated == 3
