# gold-evidence.md — Milestone 7 (Gold, local Spark reproduction)

- **Date (UTC):** 2026-09-07
- **Engine:** local PySpark 3.5.3 / Java 11
- **Command:** `python3 -m pytest tests/spark/test_silver_gold_local_spark.py::test_gold_asset_health_summary_aggregation -v`
- **Result:** **1 passed** (part of the 6-test Spark suite).

## Code parity

All Gold notebooks are **byte-identical** to the Azure reference:
`asset_health_summary.py`, `bearing_ml_features.py`, `mode_history.py`,
`detection_performance.py`, `edge_autonomy.py`, `cloud_egress.py`,
`escalation_efficacy.py` (7/7 identical). The leakage-safe ML feature logic
(`bearing_ml_features.py` + `ml/feature_spec.py`) is additionally covered by the
17 `test_feature_spec.py` tests (M1) which assert the notebook source mirrors
the normative spec.

## Logical reproduction

`test_gold_asset_health_summary_aggregation` runs the exact
`asset_health_summary.py` aggregation (group by asset_type/device/event_date;
count events; count critical) on real Spark: 3 events (1 critical) →
`total_events=3, critical_event_count=1`. PASS.

## Scenario F / B / mode-history (NOT EXECUTED end-to-end)

The full functional scenarios (Scenario F confusion matrix TP=80/FP=5/FN=10/TN=5
F1≈0.914286; Scenario B agreement=0.5; 4 mode transitions) are produced by the
synthetic generator (`tests/integration/generate_bearing_events.py`) — its
offline correctness is verified by `test_generate_bearing_events.py` (M1, 7
tests, incl. the exact Scenario F matrix). Reproducing them THROUGH the deployed
Gold evidence tables requires a live Databricks pipeline (NOT EXECUTED). The
generator-level assertions confirm the input contract; notebook parity confirms
the transformation; the gap is only the live cluster run.
