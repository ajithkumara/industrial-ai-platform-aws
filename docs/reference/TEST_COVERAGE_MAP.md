# TEST_COVERAGE_MAP.md — Current Azure Platform

> Phase 0J deliverable. What every test covers, which behaviours are
> contractual, and the PORT / ADAPT / REPLACE / N-A decision for the AWS repo.

## Automated (CI, `python -m pytest tests/`)

| Test file | Covers | Contractual? | AWS action |
|---|---|---|---|
| `test_telemetry_event.py` | Generic envelope: valid parse, arbitrary payload, required fields, `extra=forbid`, defaults, invalid JSON | YES (event contract) | **PORT** verbatim |
| `test_asset_type_config.py` | Config-driven onboarding: all 8 types load, discovery, ground_truth_label rename, new-type-needs-only-YAML, malformed→clear error, resolve_dir precedence | YES (domain-agnosticism) | **PORT** verbatim |
| `test_batch_buffer.py` | Batching + P0-01 checkpoint ordering (7 tests) | YES (delivery semantics) | **PORT** verbatim (buffer is cloud-free) |
| `test_eventhub_consumer.py` | on_event: buffer w/ partition metadata, no-checkpoint-on-buffer, failed-write, DLQ-checkpoints | YES (P0-01) | **ADAPT** → `test_kinesis_consumer.py` (shardId/seq; same assertions) |
| `test_settings_module.py` | Import safety + explicit validate | YES (lazy validation) | **ADAPT** (Kinesis/S3 settings) |
| `test_feature_spec.py` | ML feature groups, split policy, leakage, notebook mirrors spec (18) | YES (ML methodology) | **PORT** verbatim |
| `test_bearing_model_common.py` | Sigmoid transform, confusion, threshold selection (16) | YES (score contract) | **PORT** verbatim |
| `test_cwru_loader.py` | Windowing, features, split invariants (24) | YES | **PORT** verbatim |
| `test_train_bearing_isolation_forest_contract.py` | MLflow signature/input_example/UC name/log_dict/no-tmp-write | YES (MLOps deploy) | **PORT** verbatim |
| `test_generate_bearing_events.py` | Synthetic bearing event generator sanity | partial | **PORT** |
| `test_nats_bearing_bridge.py` | NATS translation: valid envelope, deterministic uuid5, priority, context sampling | YES (bridge contract) | **PORT** verbatim |
| `test_payload_sizing.py` | Escalation payload sizing / egress projections | research | **PORT** |
| `test_data_quality_scenarios.py` | DQ scenarios pass/reject vs Pydantic, DQ6 empty-id, DQ9/10 null cols | YES (DQ contract) | **PORT** verbatim |
| `tests/integration/test_send_cwru_events.py` | CWRU batching by byte size, never drop/dup, dry-run no-azure-import | YES (batching) | **ADAPT** (Kinesis 1MB record / PutRecords limits) |

## Manual smoke scripts (run directly, not CI)

`test_config.py`, `test_consumer.py`, `test_eventhub.py`, `test_settings.py`,
`test_send.py`, `test_send_bearing_events.py` — manual connectivity smoke
tests. **ADAPT** to Kinesis/S3 equivalents (or REPLACE with boto3 smoke
scripts). Not part of the CI gate.

## Integration assets (not unit tests)

`tests/integration/`: `cloud_e2e_scenario.py`, `generate_bearing_events.py`,
`data_quality_scenarios.py`, `payload_sizing.py`, `send_cwru_events.py`,
`expected_results.json`. **PORT** the pure-logic ones; **ADAPT** the senders
(Event Hubs → Kinesis).

## Coverage gaps (current)

- No automated test exercises the real ADLS `StorageClient` (only fakes) —
  same will be true for the S3 client (use `moto` in AWS port to close this).
- DLT notebooks are validated via bundle-validate + `test_feature_spec.py`
  source assertions, not executed in CI.

## AWS additions required (Phase 12)

`test_s3_storage_client.py` (moto), `test_kinesis_consumer.py`,
`test_kinesis_checkpoint.py` (DynamoDB lease via moto), reuse of all
pure-Python contract tests.
