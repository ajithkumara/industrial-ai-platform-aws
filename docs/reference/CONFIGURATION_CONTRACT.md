# CONFIGURATION_CONTRACT.md — Current Azure Platform

> Phase 0C deliverable. How environment config and asset types actually work
> in the CURRENT repo. This domain-agnostic configuration model is a core
> architectural property and MUST be preserved unchanged in the AWS port.

## Two distinct configuration systems

The repo has **two separate** configuration mechanisms. Do not conflate them.

### 1. Runtime application settings — `config/settings.py`

- Loads a `.env` file via `python-dotenv` into a single frozen dataclass
  tree: `AppSettings(eventhub, storage, consumer_batch_size, nats)`.
- Dataclasses: `EventHubSettings` (connection_string, hub_name,
  consumer_group), `StorageSettings` (account_name, connection_string,
  filesystem_name, raw_folder, raw_batch_size), `NatsSettings` (url + 4
  subjects).
- **Lazy validation contract (hardening fix):** `validate_settings()` is
  NOT called at import time. This module is imported transitively by nearly
  every package (consumer, edge, tests), including in CI where no Azure
  credentials exist. Import must be side-effect-free; only explicit entry
  points (`EventHubProducer.__init__`, `consumer...main()`) call
  `validate_settings()`. Proven by `tests/test_settings_module.py`.
- `CONSUMER_CONNECTION_STRING` prefers `EVENTHUB_CONSUMER_CONNECTION_STRING`
  (Listen-only policy) and falls back to `EVENTHUB_CONNECTION_STRING`.

### 2. Deployment/environment config-as-code — `config/environments/*.yaml`

- `dev.yaml`, `test.yaml`, `prod.yaml`, loaded by `shared/config.load_config(env)`.
- Keys: `environment`, `workspace_id`, `databricks_host`, `catalog_name`
  (fixed UC name `industrial_ai`), `storage_account_name`,
  `eventhub_namespace`, `eventhub_name`. Subscription-specific values are
  Terraform OUTPUTS, populated after apply — not fixed.

## Asset types — the domain-agnostic core (`config/asset_types/*.yml`)

**This is the single most important architectural property.** Onboarding a
new asset type (vehicle, wind turbine, PLC, pump, motor, turbine) requires
ONLY a new YAML file here — **no Python changes**.

### Shipped asset types (8)

`vehicle`, `industrial` (placeholder, empty `fields: []`), `wind_turbine`
(proof-of-concept, no producer — exists only to prove config-driven
onboarding), `bearing_sensor`, `bearing_inference`, `orchestrator_mode`,
`context_snapshot`, `cloud_validation`.

### Asset-type schema (contract)

```yaml
asset_type: vehicle              # must match TelemetryEvent.asset_type
silver_table: silver_vehicle_telemetry
primary_key: [event_id]          # default [event_id]
deduplicate: true                # default true
fields:
  - source: payload.speed_kmh    # dotted path into the Silver record
    target: speed_kmh            # output Silver column name
    type: integer                # one of SPARK_TYPE_MAP keys
  - source: payload.location.latitude   # nested paths supported
    target: latitude
    type: double
```

### Supported field types (`dlt/common/helpers.py::SPARK_TYPE_MAP`)

`string, integer/int, long/bigint, double, float, boolean/bool, timestamp,
date`. An unsupported type raises `AssetTypeConfigError` (fail fast, no
silent NULLs).

### Loader / discovery mechanics (`dlt/common/helpers.py`)

- `discover_asset_type_configs()` — globs every `*.yml`/`*.yaml`, parses and
  validates each into an `AssetTypeConfig`. This is what makes onboarding
  purely additive. A malformed config raises `AssetTypeConfigError` with an
  actionable message.
- `resolve_asset_types_dir()` — production reads the directory from the DLT
  pipeline `configuration.asset_types_config_dir` (Spark conf); local/tests
  fall back to the repo-relative path via `__file__` (lazy, because
  `__file__` is undefined inside a deployed DLT notebook).
- `FieldMapping`, `AssetTypeConfig` are frozen dataclasses.

## Deployment-time vs runtime split

- **Deployment-time**: `config/asset_types/*.yml` and
  `config/environments/*.yaml` are synced to the workspace by the Databricks
  Asset Bundle and read by the pipeline.
- **Runtime**: `.env`-driven `settings` are read by the consumer/producer
  processes.

## Contract tests that MUST be ported

`tests/test_asset_type_config.py` (24 tests) — proves every shipped config
loads, `ground_truth_label` renames, discovery finds all types, a brand-new
synthetic asset type requires only a YAML file
(`test_new_synthetic_asset_type_requires_only_a_yaml_file`), and malformed
configs raise clear errors. `tests/test_settings_module.py` — import safety +
explicit validation.

## AWS impact

- `config/asset_types/*.yml` — **copied verbatim.** Domain-agnostic, cloud-free.
- `dlt/common/helpers.py` — **copied verbatim.** No cloud dependency.
- `config/settings.py` — **adapted.** Replace `EventHubSettings` with
  `KinesisSettings` (stream_name, region, consumer/app name) and
  `StorageSettings.connection_string` with S3 bucket/prefix + region. Keep
  the frozen-dataclass shape, lazy-validation contract, and `NatsSettings`
  unchanged. Classification: **AZURE-SPECIFIC (settings) + DOMAIN-AGNOSTIC
  (asset types)**.
- `config/environments/*.yaml` — **adapted.** `eventhub_namespace/name` →
  `kinesis_stream`; `storage_account_name` → `s3_bucket`; `databricks_host`
  stays (Databricks-on-AWS workspace URL); `catalog_name` stays.
