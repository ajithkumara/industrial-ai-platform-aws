"""
Proves the config-driven asset-type architecture actually works:

  - config/asset_types/vehicle.yml loads and validates.
  - config/asset_types/industrial.yml loads and validates (even though its
    field list is currently empty pending a real industrial payload
    contract).
  - A brand-new, synthetic asset type (wind_turbine, and an ad-hoc
    "solar_panel" example built at test time) can be onboarded by adding
    ONLY a YAML file — no Python code changes — proving
    dlt/silver/flatten_payloads.py's genericity.
  - A malformed YAML configuration produces a clear, actionable error
    instead of failing silently or with an opaque traceback.

These tests exercise dlt/common/helpers.py directly via its file path
(the same technique dlt/silver/flatten_payloads.py uses) rather than a
normal `import dlt...` package import, because this repository has a
top-level directory literally named `dlt/`, which collides with the
`dlt` module Databricks injects into DLT pipeline notebooks. See the
comment at the top of dlt/silver/flatten_payloads.py for details.
"""

import importlib.util
import os
import sys
import textwrap
import types

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HELPERS_PATH = os.path.join(_REPO_ROOT, "dlt", "common", "helpers.py")
_ASSET_TYPES_DIR = os.path.join(_REPO_ROOT, "config", "asset_types")


def _load_helpers_module():
    spec = importlib.util.spec_from_file_location("_dlt_common_helpers_test", _HELPERS_PATH)
    module = importlib.util.module_from_spec(spec)
    # Register in sys.modules BEFORE exec: dataclasses (used in helpers.py)
    # resolves type hints via sys.modules[cls.__module__].
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


helpers = _load_helpers_module()


def test_vehicle_config_loads_and_validates():
    config = helpers.load_asset_type_config("vehicle", asset_types_dir=_ASSET_TYPES_DIR)
    assert config.asset_type == "vehicle"
    assert config.silver_table == "silver_vehicle_telemetry"
    assert len(config.fields) > 0
    field_sources = {f.source for f in config.fields}
    assert "payload.speed_kmh" in field_sources
    for f in config.fields:
        assert f.source.startswith("payload.")
        assert f.spark_cast_type()  # raises if the declared type is unsupported


def test_industrial_config_loads_and_validates_even_with_no_fields_yet():
    config = helpers.load_asset_type_config("industrial", asset_types_dir=_ASSET_TYPES_DIR)
    assert config.asset_type == "industrial"
    assert config.silver_table == "silver_industrial_telemetry"
    assert config.fields == []  # placeholder pending real industrial payload contract


def test_wind_turbine_config_loads_and_validates():
    config = helpers.load_asset_type_config("wind_turbine", asset_types_dir=_ASSET_TYPES_DIR)
    assert config.asset_type == "wind_turbine"
    assert config.silver_table == "silver_wind_turbine_telemetry"
    assert len(config.fields) > 0


def test_discover_asset_type_configs_finds_all_three_shipped_types():
    configs = helpers.discover_asset_type_configs(asset_types_dir=_ASSET_TYPES_DIR)
    discovered = {c.asset_type for c in configs}
    assert {"vehicle", "industrial", "wind_turbine"}.issubset(discovered)


def test_bearing_sensor_config_loads_and_validates():
    config = helpers.load_asset_type_config("bearing_sensor", asset_types_dir=_ASSET_TYPES_DIR)
    assert config.asset_type == "bearing_sensor"
    assert config.silver_table == "silver_bearing_sensor_telemetry"
    field_sources = {f.source for f in config.fields}
    assert "payload.features.rms" in field_sources
    assert "payload.label" in field_sources
    for f in config.fields:
        assert f.source.startswith("payload.")
        assert f.spark_cast_type()


def test_bearing_inference_config_loads_and_validates():
    config = helpers.load_asset_type_config("bearing_inference", asset_types_dir=_ASSET_TYPES_DIR)
    assert config.asset_type == "bearing_inference"
    assert config.silver_table == "silver_bearing_inference_results"
    field_sources = {f.source for f in config.fields}
    assert "payload.mode" in field_sources
    assert "payload.anomaly_score" in field_sources
    for f in config.fields:
        assert f.source.startswith("payload.")
        assert f.spark_cast_type()


def test_bearing_inference_uses_ground_truth_label_not_label():
    # 2026-08 rename: prediction (anomaly/anomaly_score) and ground truth
    # (the dataset's fault class) were previously adjacent, easily
    # confused columns -- both literally named "label"/nothing. This is
    # the fix; regressing it silently reintroduces a research-integrity
    # risk for F1/precision/recall evidence.
    config = helpers.load_asset_type_config("bearing_inference", asset_types_dir=_ASSET_TYPES_DIR)
    targets = {f.target for f in config.fields}
    assert "ground_truth_label" in targets
    assert "label" not in targets


def test_bearing_inference_has_forward_looking_escalation_fields():
    # These may be NULL until the real orchestrator emits them (schema-
    # aware null fallback in flatten_payloads.py) -- but the columns must
    # exist for gold.escalation_efficacy / gold.detection_performance to
    # be buildable at all.
    config = helpers.load_asset_type_config("bearing_inference", asset_types_dir=_ASSET_TYPES_DIR)
    targets = {f.target for f in config.fields}
    assert {"edge_confidence", "model_version", "policy_version", "cloud_reachable"}.issubset(
        targets
    )


def test_orchestrator_mode_config_loads_and_validates():
    config = helpers.load_asset_type_config("orchestrator_mode", asset_types_dir=_ASSET_TYPES_DIR)
    assert config.asset_type == "orchestrator_mode"
    assert config.silver_table == "silver_orchestrator_mode"
    targets = {f.target for f in config.fields}
    assert {"from_mode", "to_mode", "trigger"}.issubset(targets)
    for f in config.fields:
        assert f.source.startswith("payload.")
        assert f.spark_cast_type()


def test_context_snapshot_config_loads_and_validates():
    config = helpers.load_asset_type_config("context_snapshot", asset_types_dir=_ASSET_TYPES_DIR)
    assert config.asset_type == "context_snapshot"
    assert config.silver_table == "silver_context_snapshot"
    targets = {f.target for f in config.fields}
    assert {"rtt_ms", "cpu_pct", "cloud_reachable", "is_breach_sample"}.issubset(targets)


def test_cloud_validation_config_loads_and_validates():
    config = helpers.load_asset_type_config("cloud_validation", asset_types_dir=_ASSET_TYPES_DIR)
    assert config.asset_type == "cloud_validation"
    assert config.silver_table == "silver_cloud_validation_results"
    targets = {f.target for f in config.fields}
    # source_event_id is the correlation key back to
    # silver_bearing_inference_results.event_id -- this is what makes
    # gold.escalation_efficacy possible.
    assert {"source_event_id", "agrees_with_edge", "cloud_score"}.issubset(targets)
    for f in config.fields:
        assert f.source.startswith("payload.")
        assert f.spark_cast_type()


def test_discover_asset_type_configs_finds_bearing_types_too():
    configs = helpers.discover_asset_type_configs(asset_types_dir=_ASSET_TYPES_DIR)
    discovered = {c.asset_type for c in configs}
    assert {
        "bearing_sensor",
        "bearing_inference",
        "orchestrator_mode",
        "context_snapshot",
        "cloud_validation",
    }.issubset(discovered)


def test_new_synthetic_asset_type_requires_only_a_yaml_file(tmp_path):
    """
    THE key proof: onboard a brand-new asset type ("solar_panel") that the
    Python code has never seen, using only a YAML file dropped into an
    asset_types directory, and confirm the generic loader/flattener
    machinery in dlt/common/helpers.py handles it with zero code changes.
    """

    asset_types_dir = tmp_path / "asset_types"
    asset_types_dir.mkdir()

    (asset_types_dir / "solar_panel.yml").write_text(
        textwrap.dedent(
            """
            asset_type: solar_panel
            silver_table: silver_solar_panel_telemetry
            primary_key: [event_id]
            deduplicate: true
            fields:
              - source: payload.irradiance_w_m2
                target: irradiance_w_m2
                type: double
              - source: payload.panel_temperature_c
                target: panel_temperature_c
                type: double
              - source: payload.output_watts
                target: output_watts
                type: integer
            """
        )
    )

    config = helpers.load_asset_type_config("solar_panel", asset_types_dir=str(asset_types_dir))

    assert config.asset_type == "solar_panel"
    assert config.silver_table == "silver_solar_panel_telemetry"
    assert [f.target for f in config.fields] == [
        "irradiance_w_m2",
        "panel_temperature_c",
        "output_watts",
    ]
    # Every declared type must map to a valid Spark cast type — this is the
    # same call dlt/silver/flatten_payloads.py makes when building columns.
    for f in config.fields:
        assert f.spark_cast_type() in helpers.SPARK_TYPE_MAP.values()


def test_missing_asset_type_config_raises_clear_error():
    with pytest.raises(helpers.AssetTypeConfigError, match="No asset type configuration found"):
        helpers.load_asset_type_config("does_not_exist", asset_types_dir=_ASSET_TYPES_DIR)


def test_malformed_yaml_missing_required_keys_raises_clear_error(tmp_path):
    asset_types_dir = tmp_path / "asset_types"
    asset_types_dir.mkdir()

    # Missing `silver_table` and `fields`.
    (asset_types_dir / "broken.yml").write_text("asset_type: broken\n")

    with pytest.raises(helpers.AssetTypeConfigError, match="missing required key"):
        helpers.load_asset_type_config("broken", asset_types_dir=str(asset_types_dir))


def test_malformed_field_mapping_missing_target_raises_clear_error(tmp_path):
    asset_types_dir = tmp_path / "asset_types"
    asset_types_dir.mkdir()

    (asset_types_dir / "broken.yml").write_text(
        textwrap.dedent(
            """
            asset_type: broken
            silver_table: silver_broken_telemetry
            fields:
              - source: payload.x
                type: integer
            """
        )
    )

    with pytest.raises(helpers.AssetTypeConfigError, match="missing required key"):
        helpers.load_asset_type_config("broken", asset_types_dir=str(asset_types_dir))


def test_unsupported_field_type_raises_clear_error():
    field = helpers.FieldMapping(source="payload.x", target="x", type="not_a_real_type")
    with pytest.raises(helpers.AssetTypeConfigError, match="Unsupported field type"):
        field.spark_cast_type()


def test_invalid_yaml_syntax_raises_clear_error(tmp_path):
    asset_types_dir = tmp_path / "asset_types"
    asset_types_dir.mkdir()

    (asset_types_dir / "badsyntax.yml").write_text("asset_type: [unterminated\n  fields: -")

    with pytest.raises(helpers.AssetTypeConfigError):
        helpers.load_asset_type_config("badsyntax", asset_types_dir=str(asset_types_dir))


# ---------------------------------------------------------------------------
# resolve_asset_types_dir() — the production-safe config path resolution
# mechanism that replaced bare __file__ traversal as the default used by
# load_asset_type_config()/discover_asset_type_configs() when no explicit
# asset_types_dir is passed. See dlt/common/helpers.py and
# databricks/resources/pipelines/dlt.yml (configuration.asset_types_config_dir).
# ---------------------------------------------------------------------------


def test_resolve_asset_types_dir_falls_back_to_local_repo_path_without_spark():
    """
    With no active Spark session (the normal local/pytest environment,
    since pyspark is not a runtime dependency of this test suite),
    resolve_asset_types_dir() must fall back to the repo-relative
    config/asset_types directory and that directory must actually exist
    and contain the three shipped asset type configs.
    """

    resolved = helpers.resolve_asset_types_dir()
    assert os.path.isdir(resolved)
    assert os.path.isfile(os.path.join(resolved, "vehicle.yml"))
    assert os.path.isfile(os.path.join(resolved, "industrial.yml"))
    assert os.path.isfile(os.path.join(resolved, "wind_turbine.yml"))


def test_resolve_asset_types_dir_prefers_pipeline_configuration_value(monkeypatch):
    """
    Simulates the deployed DLT pipeline: an active Spark session whose
    configuration carries `asset_types_config_dir` (set from
    databricks/resources/pipelines/dlt.yml). resolve_asset_types_dir()
    must return that value instead of the __file__-derived local path,
    proving the pipeline-configuration parameter is the authoritative,
    deterministic mechanism in production.
    """

    deployed_path = "/Workspace/some/deployed/config/asset_types"

    class _FakeSparkConf:
        def get(self, key, default=None):
            assert key == helpers.ASSET_TYPES_CONFIG_DIR_CONF_KEY
            return deployed_path

    class _FakeSparkSession:
        conf = _FakeSparkConf()

        @staticmethod
        def getActiveSession():
            return _FakeSparkSession()

    fake_pyspark = types.ModuleType("pyspark")
    fake_pyspark_sql = types.ModuleType("pyspark.sql")
    fake_pyspark_sql.SparkSession = _FakeSparkSession
    fake_pyspark.sql = fake_pyspark_sql

    monkeypatch.setitem(sys.modules, "pyspark", fake_pyspark)
    monkeypatch.setitem(sys.modules, "pyspark.sql", fake_pyspark_sql)

    assert helpers.resolve_asset_types_dir() == deployed_path


def test_load_asset_type_config_uses_resolve_asset_types_dir_by_default(monkeypatch):
    """
    Calling load_asset_type_config() with no explicit asset_types_dir (as
    dlt/silver/flatten_payloads.py does via discover_asset_type_configs())
    must go through resolve_asset_types_dir(), not a fixed constant
    captured at import time.
    """

    monkeypatch.setattr(helpers, "resolve_asset_types_dir", lambda: _ASSET_TYPES_DIR)
    config = helpers.load_asset_type_config("vehicle")
    assert config.asset_type == "vehicle"
