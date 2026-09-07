"""
Offline tests for ml/cwru_loader.py. No .mat files or Azure connection
required — feature formulas and windowing/labeling logic are tested on
synthetic numpy arrays.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
import scipy.io as sio

from ml import cwru_loader as loader

_HAS_REAL_DATA = loader.RAW_DIR.exists() and len(list(loader.RAW_DIR.glob("*.mat"))) >= 28
_SKIP_REASON = (
    f"Real CWRU .mat files not found in {loader.RAW_DIR} (need 28). "
    "These are pre-ingestion boundary tests and require the actual "
    "downloaded dataset, not synthetic data -- see docs/thesis for the "
    "download manifest. Safe to skip where the dataset isn't present "
    "(e.g. CI), same pattern as the Python-3.10 test skips."
)


def test_label_for_filename_matches_all_four_classes():
    assert loader._label_for_filename("normal_0hp.mat") == "normal"
    assert loader._label_for_filename("inner_race_007_0hp.mat") == "inner_race"
    assert loader._label_for_filename("ball_021_3hp.mat") == "ball"
    assert loader._label_for_filename("outer_race_007_2hp.mat") == "outer_race"


def test_label_for_filename_rejects_unknown_prefix():
    with pytest.raises(ValueError):
        loader._label_for_filename("mystery_0hp.mat")


def test_windows_for_recording_drops_incomplete_final_window():
    # 5000 samples / 2048 = 2 complete windows, 904 samples dropped.
    signal = np.arange(5000, dtype=float)
    windows = loader._windows_for_recording(signal, loader.WINDOW_SAMPLES)
    assert len(windows) == 2
    assert len(windows[0]) == loader.WINDOW_SAMPLES
    assert len(windows[1]) == loader.WINDOW_SAMPLES
    # windows are non-overlapping and in order
    assert windows[0][0] == 0
    assert windows[1][0] == loader.WINDOW_SAMPLES


def test_windows_for_recording_empty_when_shorter_than_one_window():
    signal = np.arange(100, dtype=float)
    assert loader._windows_for_recording(signal, loader.WINDOW_SAMPLES) == []


def test_compute_features_on_a_known_constant_signal():
    # A constant signal has zero variance, so rms == |constant|, crest == 1.
    window = np.full(loader.WINDOW_SAMPLES, 2.0)
    features = loader._compute_features(window)
    assert features["rms"] == pytest.approx(2.0)
    assert features["peak"] == pytest.approx(2.0)
    assert features["crest"] == pytest.approx(1.0)
    assert features["variance"] == pytest.approx(0.0)
    assert features["mean_abs"] == pytest.approx(2.0)


def test_compute_features_crest_factor_definition():
    # A single large spike among near-zero samples should give a high
    # crest factor (peak far exceeds rms) -- this is the property crest
    # factor is meant to detect (impulsive bearing fault signatures).
    window = np.zeros(loader.WINDOW_SAMPLES)
    window[0] = 10.0
    features = loader._compute_features(window)
    assert features["peak"] == pytest.approx(10.0)
    assert features["crest"] > 20  # rms is small relative to the spike


def test_compute_features_never_produces_null_or_nan():
    rng = np.random.default_rng(42)
    window = rng.normal(size=loader.WINDOW_SAMPLES)
    features = loader._compute_features(window)
    for name, value in features.items():
        assert value is not None, name
        assert not (isinstance(value, float) and np.isnan(value)), name


def test_compute_features_zero_signal_does_not_raise_on_crest():
    # rms == 0 would make peak/rms a ZeroDivisionError -- must be handled,
    # not crash the whole recording's feature extraction.
    window = np.zeros(loader.WINDOW_SAMPLES)
    features = loader._compute_features(window)
    assert features["crest"] == 0.0


def test_assign_splits_is_recording_level_not_window_level():
    # Every recording of one label must land in exactly one split; the
    # function operates on filenames, not on individual windows, so this
    # is really testing that no filename can appear ambiguously.
    filenames = [
        "normal_0hp.mat", "normal_1hp.mat", "normal_2hp.mat", "normal_3hp.mat",
        "ball_007_0hp.mat", "ball_007_1hp.mat",
    ]
    splits = loader.assign_splits(filenames)
    assert set(splits) == set(filenames)
    assert all(v in ("TRAIN", "VALIDATION", "TEST") for v in splits.values())


def test_assign_splits_normal_four_files_populates_all_three_splits():
    # Regression guard mirroring test_feature_spec.py's equivalent test --
    # this is the exact real-world case (CWRU's 4-file Normal Baseline)
    # that motivated the small-N split fix.
    filenames = ["normal_0hp.mat", "normal_1hp.mat", "normal_2hp.mat", "normal_3hp.mat"]
    splits = loader.assign_splits(filenames)
    values = list(splits.values())
    assert "TRAIN" in values
    assert "VALIDATION" in values
    assert "TEST" in values


def test_assign_splits_fault_recordings_never_reach_train():
    filenames = [f"ball_007_{i}hp.mat" for i in range(4)] + [f"ball_021_{i}hp.mat" for i in range(4)]
    splits = loader.assign_splits(filenames)
    assert "TRAIN" not in splits.values()


def test_find_de_channel_prefers_highest_numeric_id_when_multiple_present():
    # Reproduces the real normal_2hp.mat quirk (bundles X098 and X099)
    # without needing the actual .mat file.
    mat = {
        "X098_DE_time": np.array([[1.0], [2.0]]),
        "X099_DE_time": np.array([[3.0], [4.0], [5.0]]),
        "__header__": b"stub",
    }
    signal = loader._find_de_channel(mat, "normal_2hp.mat")
    assert list(signal) == [3.0, 4.0, 5.0]


def test_find_de_channel_raises_when_no_de_variable_present():
    with pytest.raises(ValueError):
        loader._find_de_channel({"__header__": b"stub"}, "broken.mat")


# ---------------------------------------------------------------------------
# Pre-ingestion boundary: the 10 invariants that must hold on the REAL
# downloaded dataset before anything is sent to Event Hub. Requires the 28
# actual .mat files in data/cwru/raw/ -- skipped cleanly where they are not
# present (e.g. CI), same pattern as the platform's existing Python-3.10
# skips. These are deliberately real-data tests, not synthetic ones: the
# point is to catch a real problem in the real dataset (as happened with
# 99.mat's duplicate DE_time variable), which synthetic arrays cannot do.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def real_events_and_splits():
    if not _HAS_REAL_DATA:
        pytest.skip(_SKIP_REASON)
    events, summary = loader.build_events()
    splits = loader.assign_splits([r.source_file for r in summary])
    return events, summary, splits


@pytest.mark.skipif(not _HAS_REAL_DATA, reason=_SKIP_REASON)
def test_invariant_1_no_source_file_in_more_than_one_split(real_events_and_splits):
    events, _summary, splits = real_events_and_splits
    file_to_splits_seen: dict[str, set[str]] = {}
    for e in events:
        f = e["payload"]["file"]
        file_to_splits_seen.setdefault(f, set()).add(splits[f])
    offenders = {f: s for f, s in file_to_splits_seen.items() if len(s) > 1}
    assert offenders == {}, f"source_file(s) spanning multiple splits: {offenders}"


@pytest.mark.skipif(not _HAS_REAL_DATA, reason=_SKIP_REASON)
def test_invariant_2_train_contains_only_normal(real_events_and_splits):
    events, _summary, splits = real_events_and_splits
    train_labels = {
        e["payload"]["label"] for e in events if splits[e["payload"]["file"]] == "TRAIN"
    }
    assert train_labels == {"normal"}, f"TRAIN must be normal-only, found: {train_labels}"


@pytest.mark.skipif(not _HAS_REAL_DATA, reason=_SKIP_REASON)
def test_invariant_3_validation_contains_normal_and_fault_classes(real_events_and_splits):
    events, _summary, splits = real_events_and_splits
    val_labels = {
        e["payload"]["label"] for e in events if splits[e["payload"]["file"]] == "VALIDATION"
    }
    assert "normal" in val_labels
    assert val_labels & {"inner_race", "ball", "outer_race"}, val_labels


@pytest.mark.skipif(not _HAS_REAL_DATA, reason=_SKIP_REASON)
def test_invariant_4_test_contains_normal_and_fault_classes(real_events_and_splits):
    events, _summary, splits = real_events_and_splits
    test_labels = {
        e["payload"]["label"] for e in events if splits[e["payload"]["file"]] == "TEST"
    }
    assert "normal" in test_labels
    assert test_labels & {"inner_race", "ball", "outer_race"}, test_labels


@pytest.mark.skipif(not _HAS_REAL_DATA, reason=_SKIP_REASON)
def test_invariant_5_window_idx_unique_within_source_file(real_events_and_splits):
    events, _summary, _splits = real_events_and_splits
    seen: dict[str, set[int]] = {}
    for e in events:
        f = e["payload"]["file"]
        idx = e["payload"]["window_idx"]
        bucket = seen.setdefault(f, set())
        assert idx not in bucket, f"duplicate window_idx {idx} in {f}"
        bucket.add(idx)


@pytest.mark.skipif(not _HAS_REAL_DATA, reason=_SKIP_REASON)
def test_invariant_6_every_window_is_exactly_2048_samples():
    # Re-derive windows directly (events only carry computed features, not
    # the raw window array) to check the actual segment length used.
    filenames = loader.discover_recordings()
    checked = 0
    for filename in filenames:
        mat = sio.loadmat(loader.RAW_DIR / filename)
        signal = loader._find_de_channel(mat, filename)
        for window in loader._windows_for_recording(signal, loader.WINDOW_SAMPLES):
            assert len(window) == 2048
            checked += 1
    assert checked > 0


@pytest.mark.skipif(not _HAS_REAL_DATA, reason=_SKIP_REASON)
def test_invariant_7_sampling_rate_is_12000_for_every_event(real_events_and_splits):
    events, _summary, _splits = real_events_and_splits
    rates = {e["payload"]["sampling_rate_hz"] for e in events}
    assert rates == {12000}, rates


@pytest.mark.skipif(not _HAS_REAL_DATA, reason=_SKIP_REASON)
def test_invariant_8_all_seven_features_finite_on_real_data(real_events_and_splits):
    events, _summary, _splits = real_events_and_splits
    required = {"rms", "peak", "crest", "kurtosis", "skew", "variance", "mean_abs"}
    for e in events:
        features = e["payload"]["features"]
        assert set(features) >= required
        for name in required:
            value = features[name]
            assert math.isfinite(value), f"{e['payload']['file']} window {e['payload']['window_idx']}: {name}={value}"


@pytest.mark.skipif(not _HAS_REAL_DATA, reason=_SKIP_REASON)
def test_invariant_9_99mat_selects_x099_not_x098():
    mat = sio.loadmat(loader.RAW_DIR / "normal_2hp.mat")
    signal = loader._find_de_channel(mat, "normal_2hp.mat")
    expected = np.asarray(mat["X099_DE_time"]).reshape(-1)
    assert len(signal) == len(expected)
    assert np.array_equal(signal, expected)
    # and explicitly NOT the stray X098 data (different length -- confirmed
    # by inspection: X098 has 483903 samples, X099 has 485063)
    x098 = np.asarray(mat["X098_DE_time"]).reshape(-1)
    assert not (len(signal) == len(x098) and np.array_equal(signal, x098))


@pytest.mark.skipif(not _HAS_REAL_DATA, reason=_SKIP_REASON)
def test_invariant_10_no_waveform_key_present_yet(real_events_and_splits):
    events, _summary, _splits = real_events_and_splits
    for e in events:
        assert "waveform" not in e["payload"], (
            "This loader is the time-domain baseline only. A 'waveform' "
            "key would mean spectral/escalation payload data is being "
            "introduced silently, ahead of the CloudForest phase."
        )


@pytest.mark.skipif(not _HAS_REAL_DATA, reason=_SKIP_REASON)
def test_invariant_every_event_carries_dataset_run_id(real_events_and_splits):
    events, _summary, _splits = real_events_and_splits
    run_ids = {e["payload"]["dataset_run_id"] for e in events}
    assert run_ids == {loader.DATASET_RUN_ID}, (
        f"every event must carry the same dataset_run_id, found: {run_ids}"
    )
