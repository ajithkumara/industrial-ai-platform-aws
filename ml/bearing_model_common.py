"""
ml/bearing_model_common.py — shared, pure-Python scoring/threshold logic for
the edge bearing Isolation Forest baseline.

This module owns two things that must never drift apart between the
training script and the evaluation script:

  1. THE SCORE-DIRECTION CONTRACT.
     scikit-learn's IsolationForest.decision_function() returns HIGHER
     values for NORMAL samples and LOWER (often negative) values for
     ANOMALOUS samples -- the opposite of the convention already in use
     everywhere else in this platform (edge inference engine, CloudForest
     in ml/cloud_forest/score_escalations.py, gold.escalation_efficacy):
     anomaly_score where HIGHER = MORE ANOMALOUS.

     raw_scores_to_anomaly_scores() applies the exact same sigmoid
     transform CloudForest already uses (see score_escalations.py's
     "Same normalisation convention as the edge Inference Engine" comment):

         anomaly_score = 1 / (1 + e^(raw_score * SCORE_SIGMOID_K))

     Using a different transform here (or no transform) would make this
     baseline's anomaly_score mean something different from every other
     anomaly_score column in Bronze/Silver/Gold -- exactly the bug the
     August 2026 platform review flagged as a risk. Do not change this
     without updating score_escalations.py to match.

  2. THE THRESHOLD-SELECTION METHODOLOGY.
     Per the frozen methodology (see ml/train_bearing_isolation_forest.py's
     module docstring): a threshold is selected ONLY on VALIDATION data,
     by maximizing F1, then frozen and applied to TEST exactly once. This
     module provides the pure functions; it never reads TEST labels itself
     -- that discipline is enforced by which script calls which function
     with which data, not by anything in here.

Every function here is a pure function over plain Python floats/bools/
arrays -- no Spark, no MLflow, no sklearn import required to *use* the
threshold-selection math, so tests/test_bearing_model_common.py can run
in any Python environment, including CI, with no Databricks connection.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

FEATURE_COLUMNS = ["rms", "peak", "crest", "kurtosis", "skew", "variance", "mean_abs"]

# Matches ml/cloud_forest/score_escalations.py's cloud_scores transform
# exactly. Keep these two in sync -- see module docstring.
SCORE_SIGMOID_K = 5.0


def raw_scores_to_anomaly_scores(raw_scores) -> list[float]:
    """
    Convert IsolationForest.decision_function() output (higher = normal)
    into this platform's anomaly_score convention (higher = anomalous),
    using the same sigmoid transform as CloudForest.
    """
    return [1.0 / (1.0 + math.exp(r * SCORE_SIGMOID_K)) for r in raw_scores]


@dataclass(frozen=True)
class ConfusionCounts:
    tp: int
    fp: int
    fn: int
    tn: int

    @property
    def precision(self) -> float:
        denom = self.tp + self.fp
        return self.tp / denom if denom > 0 else 0.0

    @property
    def recall(self) -> float:
        denom = self.tp + self.fn
        return self.tp / denom if denom > 0 else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0

    def as_dict(self) -> dict:
        return {
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "tn": self.tn,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
        }


def confusion_at_threshold(
    anomaly_scores: list[float], is_actual_anomaly: list[bool], threshold: float
) -> ConfusionCounts:
    """
    A prediction is "anomaly" iff anomaly_score >= threshold (inclusive,
    so a candidate threshold equal to an observed score always flags that
    point -- matters at the boundary when candidate thresholds are drawn
    from the observed score set itself).
    """
    if len(anomaly_scores) != len(is_actual_anomaly):
        raise ValueError(
            f"anomaly_scores ({len(anomaly_scores)}) and is_actual_anomaly "
            f"({len(is_actual_anomaly)}) must be the same length"
        )
    tp = fp = fn = tn = 0
    for score, actual in zip(anomaly_scores, is_actual_anomaly):
        predicted = score >= threshold
        if predicted and actual:
            tp += 1
        elif predicted and not actual:
            fp += 1
        elif not predicted and actual:
            fn += 1
        else:
            tn += 1
    return ConfusionCounts(tp=tp, fp=fp, fn=fn, tn=tn)


@dataclass(frozen=True)
class ThresholdSelection:
    threshold: float
    validation_confusion: ConfusionCounts
    candidates_evaluated: int


def select_threshold_by_max_f1(
    anomaly_scores: list[float], is_actual_anomaly: list[bool]
) -> ThresholdSelection:
    """
    VALIDATION-ONLY threshold selection: tau* = argmax_tau F1(tau).

    Candidate thresholds are every distinct observed anomaly_score value
    in the input (a standard, exhaustive-and-correct approach for a
    piecewise-constant metric like F1 over a finite sample -- the optimal
    threshold, if one exists, is always achievable at an observed score).
    Ties on F1 are broken by preferring the threshold that also yields
    higher precision, then higher recall, then the smaller threshold
    value -- a deterministic, documented tie-break rather than
    "whichever the dict/loop order happens to produce first."

    Callers must only ever pass VALIDATION data here. This function has
    no way to enforce that itself -- it is a pure function over whatever
    scores/labels it is given -- so the caller (train_bearing_isolation_forest.py)
    is the one place this discipline is actually enforced, by simply never
    loading TEST rows before this call happens.
    """
    if not anomaly_scores:
        raise ValueError("Cannot select a threshold from an empty validation set.")

    candidates = sorted(set(anomaly_scores))
    best: ThresholdSelection | None = None

    for tau in candidates:
        confusion = confusion_at_threshold(anomaly_scores, is_actual_anomaly, tau)
        current = ThresholdSelection(
            threshold=tau,
            validation_confusion=confusion,
            candidates_evaluated=len(candidates),
        )
        if best is None:
            best = current
            continue
        best_key = (
            best.validation_confusion.f1,
            best.validation_confusion.precision,
            best.validation_confusion.recall,
            -best.threshold,
        )
        current_key = (
            current.validation_confusion.f1,
            current.validation_confusion.precision,
            current.validation_confusion.recall,
            -current.threshold,
        )
        if current_key > best_key:
            best = current

    assert best is not None  # candidates is non-empty because anomaly_scores is
    return best
