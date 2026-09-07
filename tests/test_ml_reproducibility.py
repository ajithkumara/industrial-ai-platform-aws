"""
Local ML reproducibility + leakage tests, run with the REAL scoring/threshold
logic (ml/bearing_model_common.py) and the REAL split policy (ml/feature_spec.py)
plus scikit-learn — no Databricks/MLflow required.

Verifies the ML-methodology invariants the Azure acceptance contract requires
(ACCEPTANCE_CONTRACT.md "ML acceptance invariants"), unchanged:
  - deterministic model: same seed + data -> identical anomaly scores
  - deterministic threshold: same VALIDATION -> identical frozen threshold + metrics
  - recording-level split isolation (no source_file in two splits)
  - TRAIN contains only normal; fault recordings never in TRAIN
  - is_training_eligible == (TRAIN and normal)

These are the offline halves of the Azure ML acceptance; the Databricks
train/eval JOBS (byte-identical to Azure) run on a cluster (NOT EXECUTED here).
"""

from __future__ import annotations

import numpy as np
import pytest

sklearn = pytest.importorskip("sklearn")
from sklearn.ensemble import IsolationForest

from ml.bearing_model_common import (
    FEATURE_COLUMNS,
    raw_scores_to_anomaly_scores,
    select_threshold_by_max_f1,
)
from ml import feature_spec


def _synth(n, seed, anomalous=False):
    rng = np.random.default_rng(seed)
    base = rng.normal(0.0, 1.0, size=(n, len(FEATURE_COLUMNS)))
    if anomalous:
        base = base + 6.0  # shifted cluster = anomalies
    return base


def test_model_scores_are_deterministic_for_fixed_seed():
    train = _synth(200, seed=1)
    val = _synth(50, seed=2)

    def fit_and_score():
        m = IsolationForest(n_estimators=100, random_state=42, n_jobs=1)
        m.fit(train)
        return raw_scores_to_anomaly_scores(m.decision_function(val))

    s1 = fit_and_score()
    s2 = fit_and_score()
    assert s1 == s2, "IsolationForest with a fixed seed must be reproducible"


def test_threshold_selection_is_deterministic_and_reproducible():
    # VALIDATION = normal + fault, labelled.
    normal = _synth(60, seed=3, anomalous=False)
    fault = _synth(40, seed=4, anomalous=True)
    train = _synth(200, seed=5, anomalous=False)

    X_val = np.vstack([normal, fault])
    y_val = [False] * len(normal) + [True] * len(fault)

    def freeze_threshold():
        m = IsolationForest(n_estimators=100, random_state=42, n_jobs=1)
        m.fit(train)
        scores = raw_scores_to_anomaly_scores(m.decision_function(X_val))
        return select_threshold_by_max_f1(scores, y_val)

    a = freeze_threshold()
    b = freeze_threshold()
    assert a.threshold == b.threshold
    assert a.validation_confusion.as_dict() == b.validation_confusion.as_dict()
    # sanity: a clearly-separable synthetic set should be well classified
    assert a.validation_confusion.f1 > 0.8


def test_recording_level_split_isolation_and_train_normal_only():
    # Build a corpus: several normal + several fault recordings.
    labels = ["normal"] * 6 + ["inner_race"] * 4 + ["outer_race"] * 4
    # Assign each recording a split via the REAL policy.
    assignments = {}
    for label in set(labels):
        group = [i for i, l in enumerate(labels) if l == label]
        total = len(group)
        for rank, idx in enumerate(group, start=1):
            assignments[idx] = feature_spec.assign_split(label, rank, total)

    # (1) No recording is in more than one split — trivially true (one split each),
    #     but assert the split values are valid.
    assert set(assignments.values()) <= {"TRAIN", "VALIDATION", "TEST"}

    # (2) TRAIN contains only normal recordings.
    for idx, split in assignments.items():
        if split == "TRAIN":
            assert labels[idx] == "normal", "fault recording leaked into TRAIN"

    # (3) is_training_eligible == (TRAIN and normal)
    for idx, split in assignments.items():
        elig = feature_spec.is_training_eligible(labels[idx], split)
        assert elig == (split == "TRAIN" and labels[idx] == "normal")


def test_fault_recordings_never_reach_train_across_counts():
    for total in range(1, 8):
        for rank in range(1, total + 1):
            assert feature_spec.assign_split("inner_race", rank, total) in {"VALIDATION", "TEST"}
