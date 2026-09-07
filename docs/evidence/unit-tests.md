# unit-tests.md
- **Command:** `python3 -m pytest tests/ -q`  •  **Result:** 171 passed, 11 skipped.
- Domain-core units: telemetry_event (9), asset_type_config (21), batch_buffer P0-01 (7),
  bearing_model_common (16), feature_spec (17), cwru_loader (13 + 11 skipped real-data),
  settings_module (3). All executed locally (Python 3.10). See ml/silver/ingestion evidence
  for the Spark/moto/sklearn subsets.
