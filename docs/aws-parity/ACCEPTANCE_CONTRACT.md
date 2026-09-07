# ACCEPTANCE_CONTRACT.md

> Phase 2 deliverable. The logical results the AWS implementation MUST
> reproduce. Values are taken verbatim from the Azure reference
> (`tests/integration/expected_results.json` and the three-gate DQ model in
> `tests/integration/data_quality_scenarios.py`). **These values must not be
> weakened to make AWS tests pass.** Cloud-specific metadata (offsets, S3 keys,
> shard IDs) may differ; logical results may not.

## Quality gates (identical to Azure)

- **GATE 1 — Consumer envelope validation.** Pydantic `TelemetryEvent`,
  `extra="forbid"`, `min_length=1` identity fields. Rejects invalid
  JSON / missing / extra / wrong-type / empty-id → DLQ, never reaches Bronze.
- **GATE 2 — Silver DLT expectations.** `@dlt.expect_or_drop` on identity
  fields NOT NULL + `TRIM<>''`; `to_timestamp` NULLs unparseable timestamps.
- **GATE 3 — Silver config-driven flatten.** Absent/uncastable payload field →
  typed NULL column; unknown asset_type → no flattened table but retained in
  `cleaned_telemetry_events`; never fails the pipeline.

## Data-quality scenarios (logical targets)

| ID | Scenario | Gate | In DLQ | Bronze | Cleaned | Flattened | Null cols |
|---|---|---|---|---|---|---|---|
| DQ1 | valid control | — | no | 1 | 1 | 1 | — |
| DQ2 | duplicate event | — | no | **2** | **1** | 1 | — (Bronze immutability + Silver dedup) |
| DQ3 | missing envelope field | 1 | yes | 0 | 0 | 0 | — |
| DQ4 | extra envelope field | 1 (extra=forbid) | yes | 0 | 0 | 0 | — |
| DQ5 | wrong envelope type | 1 | yes | 0 | 0 | 0 | — |
| DQ6 | empty event_id | 1 (min_length=1) | yes | 0 | 0 | 0 | — (regression guard) |
| DQ7 | unparseable timestamp | 2 | no | 1 | 0 | 0 | — |
| DQ8 | unknown asset_type | 3 | no | 1 | 1 | 0 | — (graceful degrade, no fail) |
| DQ9 | missing payload field | 3 | no | 1 | 1 | 1 | `rms` NULL |
| DQ10 | wrong payload type | 3 | no | 1 | 1 | 1 | `kurtosis` NULL |
| DQ11 | late event | — | no | 1 | 1 | 1 | — (event-time vs ingest-time) |

## Functional scenarios (from expected_results.json)

- **Scenario A (normal, CLOUD_OPTIMISED):** 10 sensor + 10 inference events;
  detection tp=0 fp=0 fn=0 tn=10.
- **Scenario B (edge-uncertain HYBRID):** 6 escalations; agreement_rate=0.5,
  edge_accuracy=0.5, cloud_accuracy=1.0, cloud_accuracy_improvement=0.5.
- **Scenario C (edge-only):** 1 mode transition, trigger=`cpu`,
  CLOUD_OPTIMISED→EDGE_ONLY, 5 inference events in window.
- **Scenario D (autonomous):** mode EDGE_AUTONOMOUS, 8 events during 14s
  outage, 1 anomaly, expected gap 2.0s.
- **Scenario E (recovery):** 2 transitions EDGE_AUTONOMOUS→HYBRID→CLOUD_OPTIMISED,
  trigger=`recovery`.
- **Scenario F (confusion matrix, CLOUD_OPTIMISED, model edge-v1.0-synthetic):**
  100 events; **TP=80, FP=5, FN=10, TN=5; precision≈0.9411765,
  recall≈0.8888889, F1≈0.9142857**.
- **CloudForest smoke:** 5 pending escalations → exactly one
  `silver_cloud_validation_results` row each; `cloud_score ∈ [0,1]`;
  `cloud_model_version` starts `cloud_forest_bearing-v`.

## Aggregate acceptance counts (Azure synthetic suite)

- **181 events** total across the acceptance run.
- **4 DLQ files** (DQ3, DQ4, DQ5, DQ6).
- **Bronze = 8**, **Silver = 6** (acceptance-run table/row expectations).
- **4 orchestration mode transitions** (C:1 + E:2 + …).
- **24 valid ML features**, **2 quarantined features**, **zero NULL feature
  columns**, **zero recording-level leakage**.

> Note: exact aggregate counts above are the Azure acceptance-run headline
> figures; the per-scenario table is the authoritative breakdown. The AWS
> end-to-end test (M7) must reproduce the per-scenario logical results; the
> headline figures are the roll-up.

## ML acceptance invariants (M8)

- Recording-level split isolation: no `source_file` in more than one split.
- TRAIN contains only `normal`; fault recordings never in TRAIN.
- VALIDATION and TEST each contain normal + fault classes.
- Every window exactly 2048 samples; sampling rate 12000 Hz.
- All seven time-domain features finite; zero NULL feature columns
  (invalid rows quarantined with reason, not NULL-filled).
- Deterministic split (same corpus → same split); deterministic seed and
  frozen threshold reproduce identical metrics.
- `dataset_run_id`, `feature_set_version` present on every feature row.

## Reproducibility contract

`dataset_run_id` + `feature_set_version` + `model_version` + frozen
`threshold` (loaded from the MLflow run artifact, never recomputed) →
identical TEST metrics on re-run.
