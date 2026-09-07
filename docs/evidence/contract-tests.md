# contract-tests.md
- Envelope contract: test_telemetry_event (9) — extra=forbid, min_length=1, defaults.
- Config-driven onboarding contract: test_asset_type_config (21) — new type = YAML only.
- P0-01 checkpoint-ordering contract: test_batch_buffer (7) + test_kinesis_consumer (4).
- ML deployment contract: test_train_bearing_isolation_forest_contract (13) — signature from
  decision_function, 3-part UC name, frozen threshold via log_dict, TEST read only by eval.
- DQ three-gate contract: test_data_quality_scenarios (16).
All PASS. Commands + detail in ml-evidence.md / ingestion-evidence.md.
