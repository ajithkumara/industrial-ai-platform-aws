"""
Regression guards for the two deployment defects that failed the first
real training run on serverless + Unity Catalog (2026-08-25), plus the
methodology invariants that must survive any future edit to the training
and evaluation scripts.

WHY SOURCE-INSPECTION TESTS: the two defects (missing UC model signature;
PermissionError writing /tmp) only manifest inside a live Databricks
notebook runtime -- they need spark, dbutils, mlflow, and a Unity Catalog
registry, none of which exist in offline CI. Re-running the notebook is
not a unit test. What CAN be pinned offline, and is exactly what
regressed, is the *contract* of the source: that log_model is called with
a signature, that no code writes to a hardcoded /tmp path, that the
registered name is a three-part UC name, and that the training script
never reads the TEST split. These assertions would have caught both
defects before deploy, and will catch a future reintroduction of either.

These complement (do not replace) tests/test_bearing_model_common.py,
which unit-tests the actual scoring/threshold math.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_TRAIN = _REPO_ROOT / "ml" / "train_bearing_isolation_forest.py"
_EVAL = _REPO_ROOT / "ml" / "evaluate_bearing_model.py"

_TRAIN_SRC = _TRAIN.read_text(encoding="utf-8")
_EVAL_SRC = _EVAL.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Defect 1: Unity Catalog requires a model signature
# ---------------------------------------------------------------------------

def test_log_model_call_includes_signature():
    # The exact omission that failed UC registration: log_model() without
    # signature=. Assert the keyword is present on the call.
    assert "signature=signature" in _TRAIN_SRC, (
        "mlflow.sklearn.log_model must be called with signature= -- Unity "
        "Catalog rejects models registered without one."
    )


def test_signature_inferred_from_decision_function_not_predict():
    # The scoring contract consumes decision_function(), never predict().
    # Signing against predict() would document an unused interface.
    assert "infer_signature(" in _TRAIN_SRC
    assert "model.decision_function(train_pdf[FEATURE_COLUMNS])" in _TRAIN_SRC
    # Guard against a regression to the reviewer's illustrative predict()
    # sketch: model.predict must not feed the signature.
    assert "infer_signature(\n        train_pdf[FEATURE_COLUMNS], model.predict(" not in _TRAIN_SRC


def test_log_model_includes_input_example():
    # input_example rounds out the signature and gives the registry a
    # concrete schema sample.
    assert "input_example=" in _TRAIN_SRC


def test_registered_model_name_is_three_part_uc_name():
    # UC model registration requires catalog.schema.model. A bare name
    # (the original defect-adjacent risk) would fail registration.
    assert "industrial_ai.ml.edge_bearing_isolation_forest" in _TRAIN_SRC


# ---------------------------------------------------------------------------
# Defect 2: /tmp is not writable on serverless compute
# ---------------------------------------------------------------------------

def test_no_hardcoded_tmp_artifact_write():
    # Check for actual write CODE, not the string itself -- the BUGFIX
    # comment deliberately quotes the old "/tmp/..." path to explain the
    # fix, so a bare substring check would false-positive on the comment.
    # Strip comment lines first, then assert no /tmp write remains.
    code_lines = [
        ln for ln in _TRAIN_SRC.splitlines() if not ln.lstrip().startswith("#")
    ]
    code_only = "\n".join(code_lines)
    assert "/tmp" not in code_only, (
        "Do not write artifacts to a hardcoded /tmp path -- serverless "
        "compute denies it. Use mlflow.log_dict()."
    )
    assert "log_artifact(" not in code_only, (
        "Use mlflow.log_dict() for the frozen threshold, not a "
        "log_artifact() of a locally-written file."
    )


def test_frozen_threshold_logged_via_log_dict():
    assert 'mlflow.log_dict(frozen, "frozen_threshold.json")' in _TRAIN_SRC


def test_frozen_dict_contains_required_reproducibility_keys():
    # Parse the `frozen = {...}` literal and assert every key the
    # evaluation script and thesis need to reproduce the run is present.
    tree = ast.parse(_TRAIN_SRC)
    frozen_keys: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if "frozen" in targets and isinstance(node.value, ast.Dict):
                frozen_keys = {
                    k.value for k in node.value.keys if isinstance(k, ast.Constant)
                }
    required = {
        "dataset_run_id",
        "feature_columns",
        "score_sigmoid_k",
        "threshold_selection_method",
        "selected_threshold",
        "validation_metrics",
    }
    assert required.issubset(frozen_keys), (
        f"frozen_threshold artifact missing keys: {required - frozen_keys}"
    )


# ---------------------------------------------------------------------------
# Methodology invariants (must survive any future edit)
# ---------------------------------------------------------------------------

def test_training_script_never_reads_test_split():
    # The whole leakage-safety argument depends on the training script not
    # touching TEST. Any filter selecting the TEST split here is a
    # methodology violation.
    assert "dataset_split = 'TEST'" not in _TRAIN_SRC
    assert 'dataset_split == "TEST"' not in _TRAIN_SRC
    assert "'TEST'" not in _TRAIN_SRC, (
        "train_bearing_isolation_forest.py must not reference the TEST "
        "split at all -- TEST is evaluated only by evaluate_bearing_model.py."
    )


def test_training_script_selects_threshold_on_validation_only():
    # Threshold selection must run against VALIDATION data.
    assert "dataset_split = 'VALIDATION'" in _TRAIN_SRC
    assert "select_threshold_by_max_f1(" in _TRAIN_SRC


def test_training_fit_uses_only_training_eligible_rows():
    # Isolation Forest is fit on normal TRAIN rows (is_training_eligible),
    # never on fault or validation/test data.
    assert "is_training_eligible = true" in _TRAIN_SRC


def test_evaluation_script_is_the_only_one_reading_test_split():
    # Symmetric to the training-side guard: TEST lives exclusively in the
    # evaluation script.
    assert "dataset_split = 'TEST'" in _EVAL_SRC


def test_evaluation_script_does_no_threshold_search():
    # The eval script must apply a frozen threshold, never search for one.
    assert "select_threshold_by_max_f1" not in _EVAL_SRC, (
        "evaluate_bearing_model.py must not select a threshold -- it applies "
        "the frozen one from the training run exactly once."
    )
    assert "confusion_at_threshold(" in _EVAL_SRC


def test_both_scripts_use_shared_score_transform():
    # Score-direction contract: both scripts must route through the shared
    # transform, not reimplement the sigmoid inline (which is how the
    # "higher=normal in one place, higher=anomalous in another" bug starts).
    assert "raw_scores_to_anomaly_scores" in _TRAIN_SRC
    assert "raw_scores_to_anomaly_scores" in _EVAL_SRC
