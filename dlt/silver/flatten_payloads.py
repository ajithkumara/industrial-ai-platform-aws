# Databricks notebook source
# flatten_payloads.py — Silver Layer (DLT): Config-Driven Payload Flattening
#
# Generic, domain-agnostic payload flattener.
#
# For every config/asset_types/<asset_type>.yml found on disk, this module
# dynamically registers one DLT table that:
#   1. reads the standardized (envelope-validated, deduplicated) Silver
#      events from `cleaned_telemetry_events`,
#   2. filters to that asset_type,
#   3. casts the configured `payload.<source>` fields to their configured
#      Spark types, aliased to the configured target column names,
#   4. writes the result to the configured `silver_table`.
#
# Adding support for a NEW asset type (e.g. wind_turbine) requires ONLY a
# new config/asset_types/<asset_type>.yml file — no changes to this file.
# There must be no "if asset_type == ..." branching here.
#
# NOTE on the import below: this file lives under a top-level directory
# named `dlt/`, and Databricks DLT pipelines inject their own module also
# named `dlt` (the `import dlt` / `@dlt.table` API) into the notebook's
# execution namespace. A normal `from dlt.common.helpers import ...`
# package import would collide with that injected module and is NOT
# reliable inside a DLT pipeline notebook context. To avoid that collision,
# dlt/common/helpers.py is loaded directly from its file path instead of
# via package import.
#
# BUGFIX: the file path used to be derived from __file__
# (os.path.dirname(os.path.abspath(__file__))), which fails with
# `NameError: name '__file__' is not defined` once this actually runs as
# a deployed DLT notebook -- __file__ is simply not defined in that
# execution context (it works locally/under pytest only because a normal
# Python import always has __file__). This file can only ever execute
# inside a Databricks DLT pipeline anyway (it imports `dlt`, which does
# not exist outside one), so there is no local-execution case to support
# here -- the pipeline's `configuration.dlt_common_dir` value
# (databricks/resources/pipelines/dlt.yml), read via spark.conf.get(), is
# used unconditionally instead.

import importlib.util
import os
import sys

import dlt
from pyspark.sql.functions import col, lit
from pyspark.sql.types import StructType

_dlt_common_dir = spark.conf.get("dlt_common_dir")
_HELPERS_PATH = os.path.join(_dlt_common_dir, "helpers.py")

_spec = importlib.util.spec_from_file_location("_dlt_common_helpers", _HELPERS_PATH)
_helpers = importlib.util.module_from_spec(_spec)
# Register in sys.modules BEFORE exec: dataclasses (used in helpers.py)
# resolves type hints via sys.modules[cls.__module__], which fails with a
# confusing AttributeError if the module isn't registered yet.
sys.modules[_spec.name] = _helpers
_spec.loader.exec_module(_helpers)

AssetTypeConfig = _helpers.AssetTypeConfig
AssetTypeConfigError = _helpers.AssetTypeConfigError
discover_asset_type_configs = _helpers.discover_asset_type_configs

# ---------------------------------------------------------------------------
# Envelope columns always carried through to every flattened Silver table.
# ---------------------------------------------------------------------------
_ENVELOPE_COLUMNS = [
    "event_id",
    "device_id",
    "asset_type",
    "timestamp",
    "priority",
    "schema_version",
]


def _source_path_exists(schema: StructType, dotted_path: str) -> bool:
    """
    Whether a dotted path (e.g. "payload.rotor_rpm") resolves against the
    given DataFrame schema.

    BUGFIX: field access like col("payload.rotor_rpm") is resolved
    statically against `payload`'s struct type, which Auto Loader infers
    purely from JSON actually observed in the landing data. If a given
    asset_type has a config/asset_types/*.yml but no device of that type
    has sent real data yet, its configured payload fields genuinely do
    not exist in the inferred schema -- referencing them directly raised
    AnalysisException [FIELD_NOT_FOUND] and failed the ENTIRE pipeline
    update, not just that one asset type's table. That defeats the
    "onboard a new asset type via YAML only" promise, since onboarding a
    type ahead of its data arriving would take the whole pipeline down.
    Used below to fall back to a typed null instead of crashing.
    """

    fields = schema.fields
    for i, part in enumerate(dotted_path.split(".")):
        match = next((f for f in fields if f.name == part), None)
        if match is None:
            return False
        if i < len(dotted_path.split(".")) - 1:
            if not isinstance(match.dataType, StructType):
                return False
            fields = match.dataType.fields
    return True


def _build_select_columns(schema: StructType, config) -> list:
    """
    Build the list of Spark columns for a single asset_type config:
    envelope columns + configured payload fields cast to their declared
    type. A configured field whose source path doesn't (yet) exist in the
    observed data's schema is emitted as a typed null column rather than
    failing the whole flow -- see _source_path_exists().
    """

    columns = [col(c) for c in _ENVELOPE_COLUMNS]

    for field_mapping in config.fields:
        cast_type = field_mapping.spark_cast_type()
        if _source_path_exists(schema, field_mapping.source):
            columns.append(
                col(field_mapping.source)
                .cast(cast_type)
                .alias(field_mapping.target)
            )
        else:
            columns.append(
                lit(None).cast(cast_type).alias(field_mapping.target)
            )

    return columns


def _make_flatten_fn(config):
    """
    Returns a zero-arg function that produces the flattened Silver DataFrame
    for a single asset_type. Bound via closure over `config` so each
    dynamically-registered DLT table gets its own asset_type/columns.
    """

    def _flatten():
        df = (
            dlt.read("industrial_ai.silver.cleaned_telemetry_events")
            .filter(col("asset_type") == config.asset_type)
        )

        select_columns = _build_select_columns(df.schema, config)

        return df.select(*select_columns)

    return _flatten


# ---------------------------------------------------------------------------
# Discover & register one DLT table per config/asset_types/*.yml.
#
# A malformed YAML configuration raises AssetTypeConfigError with a clear,
# actionable message (fail fast at pipeline-definition time) rather than
# silently skipping the asset type or producing an empty/broken table.
# ---------------------------------------------------------------------------

try:
    _ASSET_TYPE_CONFIGS = discover_asset_type_configs()
except AssetTypeConfigError as exc:
    raise AssetTypeConfigError(
        f"Failed to load config-driven asset type configuration for the "
        f"Silver flattener: {exc}"
    ) from exc

if not _ASSET_TYPE_CONFIGS:
    raise AssetTypeConfigError(
        "No asset type configurations found under config/asset_types/. "
        "At least one <asset_type>.yml is required for the Silver "
        "flattener to produce output."
    )

for _config in _ASSET_TYPE_CONFIGS:
    dlt.table(
        # BUGFIX: fully-qualified with industrial_ai.silver.* so every
        # config-driven flattened table also lands in the `silver` schema
        # regardless of the pipeline's `target: silver` default — see
        # dlt/bronze/ingest_raw_events.py for the full explanation.
        name=f"industrial_ai.silver.{_config.silver_table}",
        comment=(
            f"Config-driven flattened Silver telemetry for asset_type="
            f"'{_config.asset_type}' (source: "
            f"config/asset_types/{_config.asset_type}.yml)."
        ),
        table_properties={"quality": "silver"},
    )(_make_flatten_fn(_config))
