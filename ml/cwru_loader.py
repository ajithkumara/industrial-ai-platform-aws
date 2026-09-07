"""
CWRU dataset loader — real bearing vibration data to TelemetryEvent-shaped
events.

Reads the 28 downloaded .mat files in data/cwru/raw/, extracts the drive-end
accelerometer channel, segments each recording into fixed-length windows,
computes the seven time-domain features already defined in feature_spec.py,
and builds events in exactly the same shape translate_sensor_record()
produces for synthetic data — so the real dataset flows through the
identical event contract, Silver flattening, and Gold feature table already
proven by the cloud acceptance run.

Pure Python (numpy + scipy only), no Spark and no Azure dependency, so it
can be tested and inspected offline before anything is sent.

DEVICE ID: real CWRU windows use device_id "bearing.CWRU", deliberately
distinct from "bearing.DE"/"bearing.DQ"/"bearing.FE" used by the synthetic
test harness (tests/integration/generate_bearing_events.py). This keeps
real evaluation data trivially separable from synthetic acceptance-test
data by a single WHERE device_id = ... clause, and avoids ever repeating
the device-id fragmentation bug found and fixed during the cloud
acceptance run (see docs/runbooks/CLOUD_ACCEPTANCE_RUNBOOK.md §7.5).

DATASET_RUN_ID: every event this loader builds also carries a
dataset_run_id in its payload (see config/asset_types/bearing_sensor.yml),
defaulting to DATASET_RUN_ID below. This is a mandatory safeguard, not a
convenience -- without it, a real CWRU ingestion run lands in the exact
same Bronze/Silver/Gold tables as the synthetic acceptance data with no
column to separate them after the fact. Always filter Gold queries by
dataset_run_id when working with real-data results.

STATISTICAL NOTE -- READ BEFORE ANY EVALUATION CLAIM: this loader
produces 2,245 windows, but the independent unit of observation is the
RECORDING (28 of them), not the window. Adjacent windows within one
recording are highly correlated (near-duplicate vibration segments), which
is exactly why splitting happens at recording level (see
ml/feature_spec.py's SPLIT POLICY docstring) rather than window level. Do
not report "2,245 samples" as if it implies 2,245 independent
observations anywhere in the thesis -- state the recording count (28)
alongside the window count, every time, so a reader cannot mistake window
volume for independent sample size.

WINDOW SIZE: 2048 samples, non-overlapping. At 12 kHz this is ~0.17s per
window, matching the size already used in the CloudForest smoke-test
waveform and the payload-sizing analysis (tests/integration/payload_sizing.py).
The final partial window of each recording (fewer than 2048 samples
remaining) is dropped rather than zero-padded, since a padded window would
not be a genuine 0.17s observation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import scipy.io as sio
from scipy import stats as scipy_stats

from edge.nats_bearing_bridge import translate_sensor_record
from ml import feature_spec as spec

WINDOW_SAMPLES = 2048
SAMPLING_RATE_HZ = 12000
DEVICE_ID = "bearing.CWRU"
DATASET_RUN_ID = "cwru_exp_001"

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "cwru" / "raw"

_BASE_TS = datetime(2026, 8, 22, 6, 0, 0, tzinfo=timezone.utc)

# filename prefix -> ground_truth_label, matching config/asset_types/
# bearing_sensor.yml's payload.label -> ground_truth_label mapping.
_LABEL_FROM_PREFIX = {
    "normal": "normal",
    "inner_race": "inner_race",
    "ball": "ball",
    "outer_race": "outer_race",
}


@dataclass(frozen=True)
class RecordingWindows:
    source_file: str
    ground_truth_label: str
    n_windows: int
    n_samples: int


def _label_for_filename(filename: str) -> str:
    for prefix, label in _LABEL_FROM_PREFIX.items():
        if filename.startswith(prefix):
            return label
    raise ValueError(
        f"Cannot determine ground_truth_label from filename '{filename}' — "
        f"expected one of {sorted(_LABEL_FROM_PREFIX)} as a prefix."
    )


def _find_de_channel(mat: dict, filename: str) -> np.ndarray:
    """
    CWRU .mat files name the drive-end channel variable with the file's
    numeric ID as a prefix (e.g. 'X105_DE_time', 'X097_DE_time'), not a
    fixed name — confirmed by inspecting the actual downloaded files.
    Match by suffix instead of a literal key.

    KNOWN DATA QUIRK: CWRU's own hosted 99.mat (-> normal_2hp.mat here)
    bundles TWO variables, 'X098_DE_time' and 'X099_DE_time' — leftover
    data from 98.mat (a separate, already-downloaded file, normal_1hp.mat)
    was not cleared from the MATLAB workspace before 99.mat was saved on
    Case's server. Confirmed by inspecting all 28 downloaded files: this
    is the only one affected. When multiple candidates are present, the
    variable whose numeric prefix is largest is the file's own data (a
    file named after ID N should contain X{N}_DE_time as its primary
    channel); any lower-numbered variable is stray carryover from a
    different, already-represented recording and must be discarded rather
    than silently averaged in or arbitrarily chosen.
    """
    candidates = [k for k in mat if k.endswith("_DE_time")]
    if not candidates:
        raise ValueError(
            f"{filename}: no '*_DE_time' variable found. Keys present: "
            f"{[k for k in mat if not k.startswith('__')]}"
        )
    if len(candidates) > 1:
        chosen = max(candidates, key=lambda k: int(re.search(r"\d+", k).group()))
        print(
            f"WARNING: {filename} contains multiple DE_time variables "
            f"{sorted(candidates)} — using {chosen} (highest numeric ID, "
            f"matches this file's own identity), discarding the rest as "
            f"stray carryover from another recording."
        )
        return np.asarray(mat[chosen]).reshape(-1)
    return np.asarray(mat[candidates[0]]).reshape(-1)


def _compute_features(window: np.ndarray) -> dict[str, float]:
    rms = float(np.sqrt(np.mean(window**2)))
    peak = float(np.max(np.abs(window)))
    return {
        "rms": rms,
        "peak": peak,
        # crest factor is undefined (0/0) only if rms is exactly 0, which
        # would itself mean a dead/flat-lined sensor channel — treat as 0.0
        # rather than raising, since that is itself diagnostic information,
        # not a data-quality failure to hide.
        "crest": (peak / rms) if rms > 0 else 0.0,
        "kurtosis": float(scipy_stats.kurtosis(window, fisher=True)),
        "skew": float(scipy_stats.skew(window)),
        "variance": float(np.var(window)),
        "mean_abs": float(np.mean(np.abs(window))),
    }


def _windows_for_recording(signal: np.ndarray, window_samples: int) -> list[np.ndarray]:
    n_complete = len(signal) // window_samples
    return [
        signal[i * window_samples : (i + 1) * window_samples]
        for i in range(n_complete)
    ]


def discover_recordings(raw_dir: Path = RAW_DIR) -> list[str]:
    """Sorted list of .mat filenames present in raw_dir, for deterministic ordering."""
    if not raw_dir.exists():
        raise FileNotFoundError(f"{raw_dir} does not exist — download the CWRU files first.")
    files = sorted(p.name for p in raw_dir.glob("*.mat"))
    if not files:
        raise FileNotFoundError(f"No .mat files found in {raw_dir}.")
    return files


def assign_splits(filenames: list[str]) -> dict[str, str]:
    """
    Recording-level split assignment, using the SAME policy
    (ml/feature_spec.assign_split) that dlt/gold/bearing_ml_features.py
    applies to the whole table — computed here only so the loader's summary
    output can show the split each recording will land in; the Gold layer
    recomputes it independently from Silver, this is not authoritative.
    """
    by_label: dict[str, list[str]] = {}
    for f in filenames:
        by_label.setdefault(_label_for_filename(f), []).append(f)

    result: dict[str, str] = {}
    for label, files in by_label.items():
        files_sorted = sorted(files)  # deterministic, matches Spark's ORDER BY source_file
        total = len(files_sorted)
        for rank, f in enumerate(files_sorted, start=1):
            result[f] = spec.assign_split(label, rank, total)
    return result


def build_events(
    raw_dir: Path = RAW_DIR, dataset_run_id: str = DATASET_RUN_ID
) -> tuple[list[dict], list[RecordingWindows]]:
    """
    Returns (events, summary). events is a flat list of TelemetryEvent-shaped
    dicts (asset_type=bearing_sensor), ready to send via EventHubProducer.
    summary is one RecordingWindows entry per source file, for a sanity-check
    printout before anything is sent.

    Every event's payload carries dataset_run_id (mandatory safeguard --
    see module docstring), and deliberately does NOT carry a "waveform"
    key: the spectral/escalation payload path is a separate, later
    concern (CloudForest, HYBRID escalation) and must not be introduced
    silently through this baseline real-data loader.
    """
    filenames = discover_recordings(raw_dir)
    splits = assign_splits(filenames)

    events: list[dict] = []
    summary: list[RecordingWindows] = []
    seq = 0

    for filename in filenames:
        label = _label_for_filename(filename)
        mat = sio.loadmat(raw_dir / filename)
        signal = _find_de_channel(mat, filename)
        windows = _windows_for_recording(signal, WINDOW_SAMPLES)

        for window_idx, window in enumerate(windows):
            seq += 1
            features = _compute_features(window)
            ts = (_BASE_TS + timedelta(seconds=seq)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
            raw = {
                "ts": ts,
                "seq": seq,
                "sensor_id": DEVICE_ID,
                "file": filename,
                "label": label,
                "window_idx": window_idx,
                "features": features,
                "sampling_rate_hz": SAMPLING_RATE_HZ,
                "dataset_run_id": dataset_run_id,
            }
            events.append(translate_sensor_record(raw))

        summary.append(
            RecordingWindows(
                source_file=filename,
                ground_truth_label=label,
                n_windows=len(windows),
                n_samples=len(signal),
            )
        )

    return events, summary


def print_summary(summary: list[RecordingWindows], splits: dict[str, str]) -> None:
    print(f"{'source_file':<28} {'label':<12} {'split':<11} {'windows':>8} {'samples':>9}")
    print("-" * 72)
    total_windows = 0
    for r in summary:
        print(
            f"{r.source_file:<28} {r.ground_truth_label:<12} "
            f"{splits[r.source_file]:<11} {r.n_windows:>8} {r.n_samples:>9}"
        )
        total_windows += r.n_windows
    print("-" * 72)
    print(f"{'TOTAL':<28} {'':<12} {'':<11} {total_windows:>8}")

    by_label_split: dict[tuple[str, str], int] = {}
    for r in summary:
        key = (r.ground_truth_label, splits[r.source_file])
        by_label_split[key] = by_label_split.get(key, 0) + r.n_windows
    print()
    print("Windows by (label, split):")
    for (label, split), n in sorted(by_label_split.items()):
        print(f"  {label:<12} {split:<11} {n}")


if __name__ == "__main__":
    events, summary = build_events()
    splits = assign_splits([r.source_file for r in summary])
    print_summary(summary, splits)
    print(f"\ndataset_run_id: {DATASET_RUN_ID}")
    print(f"{len(events)} events built from {len(summary)} recordings (not sent).")
    print(
        f"NOTE: {len(events)} windows, but {len(summary)} independent "
        f"recordings -- report both, always, in any evaluation write-up."
    )
