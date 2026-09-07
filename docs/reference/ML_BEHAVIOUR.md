# ML_BEHAVIOUR.md — Current Azure Platform

> Phase 0G deliverable. The full current ML implementation. The AWS port must
> preserve this behaviour unless an AWS-specific change is technically
> necessary. This is NOT scaffolding — it is a disciplined, leakage-safe,
> reproducible ML methodology.

## Components

| File | Role | Compute |
|---|---|---|
| `ml/feature_spec.py` | Normative spec (pure Python) for feature groups, validity, split policy | offline/CI |
| `dlt/gold/bearing_ml_features.py` | Spark implementation of feature_spec, produces the Gold feature table | DLT |
| `ml/bearing_model_common.py` | Pure-Python score transform + threshold selection | offline/CI |
| `ml/train_bearing_isolation_forest.py` | Edge baseline: fit IF, select+freeze threshold, register model | Databricks Job |
| `ml/evaluate_bearing_model.py` | One-time frozen-threshold TEST evaluation | Databricks Job |
| `ml/cloud_forest/train_cloud_forest.py` | Heavier cloud validation IF model | Databricks Job |
| `ml/cloud_forest/score_escalations.py` | Async batch scoring of HYBRID escalations → cloud_validation events | Databricks Job |
| `ml/cwru_loader.py` | Real CWRU .mat → TelemetryEvent windows (numpy/scipy) | offline |
| `ml/feature_store_setup.py`, `ml/train_anomaly_model.py` | SUPERSEDED stubs (marked for deletion) | — |

## Feature groups (`feature_spec.py`) — the leakage contract

- **time_domain** (model inputs): `rms, peak, crest, kurtosis, skew,
  variance, mean_abs`. Computed at the edge, so an edge-trained model can run
  at the edge.
- **trend** (derived, strictly backward-looking): `rms_roll_mean_5,
  rms_roll_std_5, rms_delta_1, kurtosis_roll_mean_5`; window = current + 4
  preceding rows only (`rowsBetween(-4,0)`). A window including future rows
  would leak.
- **spectral**: cloud-side advantage from raw waveform; deliberately NOT in
  this table (mostly-NULL otherwise).
- **context** (FORBIDDEN in the feature table): `mode, rtt_ms, cpu_pct,
  cloud_reachable, edge_confidence, anomaly, anomaly_score, edge/cloud
  decisions, infer_ms`. These are what the research evaluates — training on
  them would be circular. Enforced by `test_feature_spec.py` against notebook
  source.
- **evaluation**: `ground_truth_label`, `is_actual_anomaly` — present but
  never a model input (IF is unsupervised).

## Validity — quarantine, never NULL-fill

`REQUIRED_NON_NULL` = time_domain + `event_id, source_file,
ground_truth_label, window_idx`. A row missing any is routed to
`bearing_ml_features_quarantine` with the offending columns named. DQ9/DQ10
showed missing vs uncastable fields both surface as NULL and are
indistinguishable — so the feature layer rejects rather than imputes.

## Split policy — recording-level, stratified, deterministic

Grouping key is `source_file` (the CWRU recording), NOT the window: adjacent
windows are near-duplicates, so a window-level random split inflates every
metric (the most common bearing-ML methodological failure). Stratified by
label. **Fault recordings never enter TRAIN** (IF fitted on normal only).
- normal: 60% TRAIN / 20% VALIDATION / 20% TEST
- fault: 50% VALIDATION / 50% TEST
- Small-N guarantee: CWRU Normal Baseline has exactly 4 recordings; explicit
  assignment below total=5 so no split is starved (`assign_split`).
VALIDATION selects the threshold; TEST is touched exactly once.

## Score-direction contract (`bearing_model_common.py`)

`IsolationForest.decision_function()` returns higher=normal. The platform
convention is higher=anomalous everywhere (edge, CloudForest, gold). Both
edge and cloud apply the SAME sigmoid: `anomaly_score = 1/(1 + e^(raw *
SCORE_SIGMOID_K))`, `SCORE_SIGMOID_K = 5.0`. Keep edge and cloud in sync.

## Threshold methodology (frozen)

`select_threshold_by_max_f1` — candidates are every distinct observed
VALIDATION score; `tau* = argmax F1`; deterministic tie-break (precision,
then recall, then smaller tau). Selected on VALIDATION only, frozen, applied
to TEST once. `evaluate_bearing_model.py` loads the frozen threshold from the
train run's MLflow artifact (`frozen_threshold.json` via `log_dict`) — never
recomputes, cannot drift. Requires explicit `train_run_id` (no "latest").

## Training script contract (`train_bearing_isolation_forest.py`)

Loads TRAIN (`is_training_eligible=true`) + VALIDATION only — never TEST.
Fits IF on time_domain features. Logs params/metrics, frozen threshold via
`log_dict`, and registers the model with `infer_signature` derived from
`decision_function` (not `predict`) to the three-part UC name
`industrial_ai.ml.edge_bearing_isolation_forest`. Regression guards in
`tests/test_train_bearing_isolation_forest_contract.py`.

## CloudForest (`ml/cloud_forest/`)

Heavier IF (more trees, full feature set, no latency budget) — same
algorithm family, swappable behind the `cloud_validation` event contract.
`score_escalations.py` reads HYBRID `silver_bearing_inference_results`, joins
`silver_bearing_sensor_telemetry` on device_id+seq, re-scores, and writes one
`cloud_validation` event into the SAME ADLS landing path (flows through the
normal pipeline). Architectural invariant: async, read-only w.r.t. the edge
decision — never blocks/overrides it.

## CWRU loader (`ml/cwru_loader.py`)

Pure numpy/scipy. 28 .mat files → drive-end channel → 2048-sample
non-overlapping windows (12 kHz) → 7 time-domain features → TelemetryEvents
with `device_id="bearing.CWRU"` and a mandatory `dataset_run_id`. 2,245
windows from 28 recordings — recording is the independent unit, not window.

## Contract tests that MUST be ported

`test_feature_spec.py` (18), `test_bearing_model_common.py` (16),
`test_cwru_loader.py` (24 incl. invariants), `test_generate_bearing_events.py`,
`test_train_bearing_isolation_forest_contract.py`,
`test_payload_sizing.py`.

## AWS impact

- `feature_spec.py`, `bearing_model_common.py`, `cwru_loader.py` — **copied
  verbatim** (pure Python, no cloud).
- `dlt/gold/bearing_ml_features.py` — **copied verbatim** (PySpark).
- Training/eval/CloudForest notebooks — **copied verbatim**; MLflow +
  UC three-part names work identically on Databricks-on-AWS. `score_escalations.py`
  `bronze_path` → S3 URI (bundle var). MLflow tracking is the workspace's
  managed MLflow on either cloud. Classification: **SHARED / DATABRICKS-SPECIFIC,
  cloud-invariant except the S3 landing URI.**
