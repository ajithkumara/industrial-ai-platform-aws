"""
Tests for ml/feature_spec.py and its Spark implementation in
dlt/gold/bearing_ml_features.py.

Two jobs:

  1. Verify the split policy behaves correctly -- stratified, deterministic,
     recording-level, and with no fault recording ever reaching TRAIN.

  2. Guard against DRIFT between the normative spec and the notebook. The
     notebook cannot import feature_spec.py directly (it executes inside a
     DLT pipeline where package imports from the repo are unreliable -- see
     the note at the top of dlt/silver/flatten_payloads.py), so it mirrors
     the constants. These tests read the notebook's source and assert the
     mirrored values still match, which is what makes the duplication safe.
"""

from __future__ import annotations

import os
import re
from collections import Counter

from ml import feature_spec as spec

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_NOTEBOOK = os.path.join(_REPO_ROOT, "dlt", "gold", "bearing_ml_features.py")


def _notebook_source() -> str:
    with open(_NOTEBOOK, encoding="utf-8") as fh:
        return fh.read()


# ---------------------------------------------------------------------------
# Split policy behaviour
# ---------------------------------------------------------------------------


def test_fault_recordings_never_reach_train():
    """
    The core unsupervised guarantee. Isolation Forest is fitted on normal
    data only; a fault recording in TRAIN would both violate that premise
    and leak evaluation data into fitting.
    """
    for label in ("ball", "inner_race", "outer_race"):
        for total in range(1, 30):
            for rank in range(1, total + 1):
                assert spec.assign_split(label, rank, total) != spec.SPLIT_TRAIN


def test_normal_recordings_populate_all_three_splits():
    total = 10
    splits = [spec.assign_split("normal", r, total) for r in range(1, total + 1)]
    counts = Counter(splits)
    assert counts[spec.SPLIT_TRAIN] == 6
    assert counts[spec.SPLIT_VALIDATION] == 2
    assert counts[spec.SPLIT_TEST] == 2


def test_fault_recordings_split_evenly_between_validation_and_test():
    total = 8
    splits = [spec.assign_split("ball", r, total) for r in range(1, total + 1)]
    counts = Counter(splits)
    assert counts[spec.SPLIT_VALIDATION] == 4
    assert counts[spec.SPLIT_TEST] == 4


def test_split_assignment_is_deterministic():
    a = [spec.assign_split("normal", r, 7) for r in range(1, 8)]
    b = [spec.assign_split("normal", r, 7) for r in range(1, 8)]
    assert a == b


def test_every_fault_class_appears_in_evaluation_splits():
    """
    Stratification guarantee: each class must be represented in the splits
    used for threshold selection and final evaluation, otherwise recall for
    an absent class is unmeasurable.
    """
    for label in ("ball", "inner_race", "outer_race"):
        splits = {spec.assign_split(label, r, 4) for r in range(1, 5)}
        assert spec.SPLIT_VALIDATION in splits
        assert spec.SPLIT_TEST in splits


def test_single_recording_edge_case_does_not_crash():
    # Degenerate but real during early data collection: one recording per
    # class. A normal recording goes to TRAIN; a fault one to VALIDATION.
    assert spec.assign_split("normal", 1, 1) == spec.SPLIT_TRAIN
    assert spec.assign_split("ball", 1, 1) == spec.SPLIT_VALIDATION


def test_four_normal_recordings_populate_all_three_splits():
    """
    Regression guard for the real CWRU dataset. Normal Baseline has
    exactly 4 recordings and no more exist to download at this sample
    rate. The general 60/20/20 ratio formula silently produces ZERO TEST
    recordings at total=4 (position sequence 0, .25, .5, .75 -> 3 TRAIN /
    1 VALIDATION / 0 TEST), which would make true negatives and false
    positives unmeasurable in the final held-out evaluation. This is the
    single most consequential split-policy bug this dataset could have
    shipped with, since it would silently invalidate every precision/
    specificity figure computed from TEST -- caught before real training
    data was generated.
    """
    splits = [spec.assign_split("normal", r, 4) for r in range(1, 5)]
    assert splits == [
        spec.SPLIT_TRAIN,
        spec.SPLIT_TRAIN,
        spec.SPLIT_VALIDATION,
        spec.SPLIT_TEST,
    ]
    counts = Counter(splits)
    assert counts[spec.SPLIT_TEST] >= 1, (
        "Normal class must have at least one TEST recording, or the final "
        "confusion matrix cannot report true negatives or false positives."
    )


def test_small_normal_recording_counts_never_starve_a_split():
    # total=2 and total=3 are lower-probability but should degrade
    # gracefully rather than reproducing the total=4 bug at a different N.
    assert [spec.assign_split("normal", r, 2) for r in range(1, 3)] == [
        spec.SPLIT_TRAIN,
        spec.SPLIT_VALIDATION,
    ]
    assert [spec.assign_split("normal", r, 3) for r in range(1, 4)] == [
        spec.SPLIT_TRAIN,
        spec.SPLIT_VALIDATION,
        spec.SPLIT_TEST,
    ]


def test_out_of_range_rank_is_rejected():
    import pytest

    with pytest.raises(ValueError):
        spec.assign_split("normal", 0, 5)
    with pytest.raises(ValueError):
        spec.assign_split("normal", 6, 5)
    with pytest.raises(ValueError):
        spec.assign_split("normal", 1, 0)


def test_training_eligibility_requires_both_train_split_and_normal_label():
    assert spec.is_training_eligible("normal", spec.SPLIT_TRAIN) is True
    assert spec.is_training_eligible("ball", spec.SPLIT_TRAIN) is False
    assert spec.is_training_eligible("normal", spec.SPLIT_VALIDATION) is False
    assert spec.is_training_eligible("normal", spec.SPLIT_TEST) is False


# ---------------------------------------------------------------------------
# Leakage guarantees
# ---------------------------------------------------------------------------


def test_no_context_or_outcome_column_is_selected_by_the_notebook():
    """
    The central leakage guarantee. If someone later adds `edge_confidence`
    or `anomaly_score` to the feature table -- plausibly with good
    intentions, e.g. "for convenience in evaluation" -- every model trained
    on it becomes circular and the C4 result becomes meaningless. This test
    makes that change fail loudly.
    """
    source = _notebook_source()
    # Consider only the projection, not the explanatory comments (which
    # legitimately name these columns when explaining why they are absent).
    code_lines = [
        ln for ln in source.splitlines() if not ln.strip().startswith("#")
    ]
    code = "\n".join(code_lines)

    for forbidden in spec.FORBIDDEN_CONTEXT_COLUMNS:
        assert f'"{forbidden}"' not in code, (
            f"'{forbidden}' is a context/outcome column and must never be "
            f"selected into bearing_ml_features -- see ml/feature_spec.py."
        )


def test_trend_features_use_a_backward_only_window():
    """
    rowsBetween(-(N-1), 0) is causal. Anything with a positive upper bound
    (e.g. rowsBetween(-2, 2)) would include future rows and leak.
    """
    source = _notebook_source()
    assert "rowsBetween(-(TREND_WINDOW_ROWS - 1), 0)" in source
    # No window may extend forwards.
    forward = re.findall(r"rowsBetween\(\s*[^,]+,\s*([^)]+)\)", source)
    for upper in forward:
        assert upper.strip() in {"0", "Window.currentRow"}, (
            f"trend window upper bound '{upper}' extends into the future"
        )


def test_split_is_assigned_on_recording_not_window():
    source = _notebook_source()
    # The split must be derived from distinct recordings and joined back,
    # never computed per-row over the full window-level dataframe.
    assert 'select("source_file", "ground_truth_label").distinct()' in source
    assert 'on=["source_file", "ground_truth_label"]' in source


# ---------------------------------------------------------------------------
# Spec / notebook drift guards
# ---------------------------------------------------------------------------


def test_notebook_mirrors_the_spec_constants():
    source = _notebook_source()

    def literal(name: str) -> str:
        match = re.search(rf"^{name} = (.+)$", source, re.MULTILINE)
        assert match, f"{name} not found in {_NOTEBOOK}"
        return match.group(1).strip()

    assert literal("TREND_WINDOW_ROWS") == str(spec.TREND_WINDOW_ROWS)
    assert literal("NORMAL_TRAIN_RATIO") == str(spec.NORMAL_TRAIN_RATIO)
    assert literal("NORMAL_VALIDATION_RATIO") == str(spec.NORMAL_VALIDATION_RATIO)
    assert literal("FAULT_VALIDATION_RATIO") == str(spec.FAULT_VALIDATION_RATIO)
    assert literal("NORMAL_LABEL") == f'"{spec.NORMAL_LABEL}"'
    assert literal("FEATURE_SET_VERSION") == f'"{spec.FEATURE_SET_VERSION}"'


def test_notebook_time_domain_features_match_the_spec():
    source = _notebook_source()
    match = re.search(
        r"TIME_DOMAIN_FEATURES = \[(.*?)\]", source, re.DOTALL
    )
    assert match
    names = re.findall(r'"(\w+)"', match.group(1))
    assert tuple(names) == spec.TIME_DOMAIN_FEATURES


def test_notebook_required_non_null_matches_the_spec():
    source = _notebook_source()
    match = re.search(r"REQUIRED_NON_NULL = TIME_DOMAIN_FEATURES \+ \[(.*?)\]", source, re.DOTALL)
    assert match
    extra = re.findall(r'"(\w+)"', match.group(1))
    assert tuple(spec.TIME_DOMAIN_FEATURES) + tuple(extra) == spec.REQUIRED_NON_NULL


def test_quarantine_table_exists_and_is_the_complement_of_the_feature_table():
    source = _notebook_source()
    assert "bearing_ml_features_quarantine" in source
    # One side keeps valid rows, the other keeps their complement.
    assert 'filter(F.col("is_valid"))' in source
    assert 'filter(~F.col("is_valid"))' in source
