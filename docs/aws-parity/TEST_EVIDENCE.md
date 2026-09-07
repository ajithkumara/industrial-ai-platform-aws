# TEST_EVIDENCE.md

> Executed evidence per milestone. Nothing here is aspirational — every row
> is a command that was actually run, with its real result. A capability is
> only marked VERIFIED in PARITY_MATRIX.md when it appears here.

## Milestone 1 — Repository + Domain Core

- **Environment:** Python 3.10.12, Linux 6.8.0 (x86_64), pytest 8.x
- **Timestamp (UTC):** 2026-09-07T03:33:10Z
- **Working dir:** `industrial-ai-platform-aws/`
- **Evidence location:** this document; reproduce with the commands below.

### E1 — Unit / contract / schema / DQ / ML test suite

Command:
```
python3 -m pytest tests/ -v
```
Result: **129 passed, 11 skipped, 0 failed** (2 benign scipy precision
warnings on a constant-signal feature test — present in the Azure reference too).

Per-file breakdown (all passing):

| Test file | Tests | Covers (contract) |
|---|---|---|
| test_telemetry_event.py | 9 | Generic envelope: required fields, `extra=forbid`, defaults, invalid JSON, arbitrary-payload domain-agnosticism |
| test_asset_type_config.py | 21 | Config-driven onboarding: all 8 asset types load, discovery, new-type-needs-only-YAML, malformed→clear error, resolve-dir precedence |
| test_batch_buffer.py | 7 | Batching + **P0-01 checkpoint ordering** (no checkpoint on partial buffer; checkpoint after durable write per partition; no checkpoint on failed write) |
| test_bearing_model_common.py | 16 | Sigmoid score transform, confusion counts, max-F1 threshold selection + deterministic tie-break |
| test_feature_spec.py | 17 | ML feature groups, leakage exclusion, recording-level split policy, notebook mirrors spec constants |
| test_cwru_loader.py | 24 | Windowing, 7 time-domain features, split invariants (13 offline **passed**, 11 real-`.mat`-data tests **skipped** — see E2) |
| test_data_quality_scenarios.py | 16 | Three-gate DQ model, DQ6 empty-id regression guard, DQ9/DQ10 null-column expectations |
| test_generate_bearing_events.py | 7 | Synthetic scenario generator: Scenario F confusion matrix (TP=80/FP=5/FN=10/TN=5), Scenario B agreement=0.5 |
| test_nats_bearing_bridge.py | 14 | Pure translate_* functions: deterministic uuid5, priority mapping, context-snapshot breach/heartbeat sampling |
| test_payload_sizing.py | 6 | Escalation payload sizing / egress projections |
| test_settings_module.py | 3 | **AWS-adapted**: import safety (no env vars required), explicit `validate_settings()` for KINESIS_STREAM_NAME/S3_BUCKET/AWS_REGION |

### E2 — Skipped tests (honest disclosure)

11 tests in `test_cwru_loader.py` **skipped** with reason: real CWRU `.mat`
files not present (`data/cwru/raw/`, need 28). These are pre-ingestion
boundary tests requiring the actual downloaded dataset, not synthetic data —
they skip identically in the Azure reference's CI. Not a failure; not counted
as verified. They will be exercised in M8 with the dataset present.

### E3 — Static analysis

Commands:
```
python3 -m py_compile <all domain modules>
python3 -m pyflakes shared config consumer edge ml dlt
```
Result: **all modules compile.** Pyflakes findings: 2, both **inherited
verbatim from the Azure reference** (not introduced by the port):
`consumer/batch_buffer.py:49 defaultdict imported but unused`,
`ml/cwru_loader.py:212 local 'splits' assigned but never used`. Logged as
lint-cleanup item F-M1-01 in HARDENING_BACKLOG (P3); no behavioural impact.

### E4 — Domain / cloud decoupling gate

Command:
```
grep -rnE "^\s*(import|from)\s+(boto3|botocore|azure)" shared/ config/ ml/ dlt/ consumer/batch_buffer.py
```
Result: **zero matches.** No AWS or Azure SDK import has leaked into the
domain core. The concrete cloud clients (Kinesis producer/consumer, S3
storage client) arrive at the infrastructure boundary in Milestone 2; the
`StorageClient` type reference in `batch_buffer.py` is `TYPE_CHECKING`-guarded.

### E5 — Dependency / security scan

Command:
```
python3 -m pip_audit -r requirements.txt
```
Result: **No known vulnerabilities found.**

## Verification status after M1

| Capability | State | Basis |
|---|---|---|
| Generic envelope | VERIFIED | E1 (9/9) |
| Config-driven asset types | VERIFIED | E1 (21/21) |
| Batch buffer + P0-01 ordering | VERIFIED | E1 (7/7) |
| ML feature spec / split policy | VERIFIED | E1 (17/17) |
| Score/threshold logic | VERIFIED | E1 (16/16) |
| DQ three-gate contract | VERIFIED | E1 (16/16) |
| NATS translate logic | VERIFIED | E1 (14/14) |
| CWRU loader (offline) | VERIFIED | E1 (13/13); real-data PARTIAL (E2) |
| AWS settings (lazy validation) | VERIFIED | E1 (3/3) |
| Domain/cloud decoupling | VERIFIED | E4 |

**Gate M1: PASS.** Proceed to Milestone 2 (AWS ingestion) permitted.
