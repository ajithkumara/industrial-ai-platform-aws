"""
DLT Common Helpers

Reusable, domain-agnostic mechanics shared across Bronze/Silver/Gold DLT
pipelines. This module must NOT contain any asset-type-specific logic
(no "if asset_type == ..." branches, no hardcoded vehicle/industrial/
wind_turbine field names). Domain knowledge belongs exclusively in
config/asset_types/<asset_type>.yml.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _local_dev_asset_types_dir() -> str:
    """
    Local development / unit-test fallback ONLY. Once this code is deployed
    and running inside the DLT pipeline, resolve_asset_types_dir() below
    never reaches this: the deployed pipeline supplies the directory
    explicitly and deterministically via its `configuration` block (see
    databricks/resources/pipelines/dlt.yml ->
    configuration.asset_types_config_dir).

    BUGFIX: this used to compute a module-level constant via __file__ at
    *import* time, unconditionally -- including when this module is loaded
    inside a deployed DLT notebook, where __file__ is simply not defined
    (confirmed: `NameError: name '__file__' is not defined` at pipeline-run
    time, even though the exact same code runs fine locally/under pytest,
    where a normal Python import always has __file__). Now computed lazily,
    only when this fallback path is actually taken (no active Spark
    session / no pipeline configuration value present), which never
    happens once this is running inside the deployed pipeline.
    """
    try:
        this_file = __file__
    except NameError as exc:
        raise RuntimeError(
            "resolve_asset_types_dir() fell through to the local-dev "
            "__file__-based fallback, but __file__ is not defined in this "
            "execution context. This fallback is only valid locally/under "
            "pytest -- in a deployed DLT pipeline, the "
            "asset_types_config_dir pipeline configuration value "
            "(databricks/resources/pipelines/dlt.yml) must be set and "
            "readable via spark.conf.get(), which should have been used "
            "instead of ever reaching this fallback."
        ) from exc
    # dlt/common/helpers.py -> repo root is two levels up (dlt/common -> dlt -> root)
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(this_file))))
    return os.path.join(repo_root, "config", "asset_types")


# Name of the DLT pipeline `configuration` key (see
# databricks/resources/pipelines/dlt.yml) that carries the deployed,
# absolute path to config/asset_types/. Databricks exposes DLT pipeline
# `configuration` key/value pairs to pipeline code as Spark configuration
# properties, so this is read via spark.conf.get() in
# resolve_asset_types_dir().
ASSET_TYPES_CONFIG_DIR_CONF_KEY = "asset_types_config_dir"


def resolve_asset_types_dir() -> str:
    """
    Determine the directory containing config/asset_types/*.yml.

    Production (deployed DLT pipeline): the directory is supplied
    explicitly and deterministically via the DLT pipeline's
    `configuration` block (databricks/resources/pipelines/dlt.yml ->
    configuration.asset_types_config_dir). The Databricks Asset Bundle
    guarantees config/asset_types/ is synced to the workspace via the
    explicit `sync.include` entry in databricks/databricks.yml. This is
    the production-safe, deterministic replacement for walking up from
    __file__.

    Local development / unit tests: no Spark session is active and no
    pipeline configuration exists, so this falls back to the
    repo-relative path derived from __file__. That fallback is never
    exercised once the code is actually running inside the deployed DLT
    pipeline, because the pipeline configuration value is always present
    there.
    """

    try:
        from pyspark.sql import SparkSession

        spark = SparkSession.getActiveSession()
        if spark is not None:
            configured = spark.conf.get(ASSET_TYPES_CONFIG_DIR_CONF_KEY, None)
            if configured:
                return configured
    except ImportError:
        pass

    return _local_dev_asset_types_dir()


def __getattr__(name: str):
    # Backwards-compatible lazy module attribute. Reflects the local/dev
    # fallback path only; production code goes through
    # resolve_asset_types_dir() (used as the default in
    # load_asset_type_config/discover_asset_type_configs) so the
    # pipeline-configuration value is honored when present. Lazy (PEP 562)
    # so merely importing this module never touches __file__ -- only
    # accessing helpers.ASSET_TYPES_DIR directly does.
    if name == "ASSET_TYPES_DIR":
        return _local_dev_asset_types_dir()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

# Mapping of the type names allowed in config/asset_types/*.yml to Spark SQL
# cast type strings. Keeping this table small and explicit makes malformed
# config fail fast with a clear error instead of silently producing NULLs.
SPARK_TYPE_MAP: dict[str, str] = {
    "string": "string",
    "integer": "int",
    "int": "int",
    "long": "bigint",
    "bigint": "bigint",
    "double": "double",
    "float": "float",
    "boolean": "boolean",
    "bool": "boolean",
    "timestamp": "timestamp",
    "date": "date",
}


class AssetTypeConfigError(ValueError):
    """Raised when an asset_type YAML configuration is missing or malformed."""


@dataclass(frozen=True)
class FieldMapping:
    source: str
    target: str
    type: str

    def spark_cast_type(self) -> str:
        try:
            return SPARK_TYPE_MAP[self.type.lower()]
        except KeyError as exc:
            raise AssetTypeConfigError(
                f"Unsupported field type '{self.type}' for target column "
                f"'{self.target}'. Supported types: {sorted(SPARK_TYPE_MAP)}"
            ) from exc


@dataclass(frozen=True)
class AssetTypeConfig:
    asset_type: str
    silver_table: str
    fields: list[FieldMapping] = field(default_factory=list)
    primary_key: list[str] = field(default_factory=lambda: ["event_id"])
    deduplicate: bool = True


# ---------------------------------------------------------------------------
# Config loading / validation
# ---------------------------------------------------------------------------


def _validate_raw_config(raw: dict[str, Any], source_path: str) -> None:
    if not isinstance(raw, dict):
        raise AssetTypeConfigError(
            f"Asset type config '{source_path}' must be a YAML mapping, "
            f"got {type(raw).__name__}."
        )

    required_top_level = ("asset_type", "silver_table", "fields")
    missing = [k for k in required_top_level if k not in raw]
    if missing:
        raise AssetTypeConfigError(
            f"Asset type config '{source_path}' is missing required key(s): "
            f"{missing}. Every config/asset_types/*.yml must define "
            f"asset_type, silver_table, and fields."
        )

    if raw["fields"] is None:
        raw["fields"] = []

    if not isinstance(raw["fields"], list):
        raise AssetTypeConfigError(
            f"Asset type config '{source_path}': 'fields' must be a list."
        )

    for i, f in enumerate(raw["fields"]):
        if not isinstance(f, dict):
            raise AssetTypeConfigError(
                f"Asset type config '{source_path}': fields[{i}] must be a "
                f"mapping, got {type(f).__name__}."
            )
        required_field_keys = ("source", "target", "type")
        missing_field_keys = [k for k in required_field_keys if k not in f]
        if missing_field_keys:
            raise AssetTypeConfigError(
                f"Asset type config '{source_path}': fields[{i}] is missing "
                f"required key(s): {missing_field_keys}. Every field mapping "
                f"must define source, target, and type."
            )


def parse_asset_type_config(raw: dict[str, Any], source_path: str = "<memory>") -> AssetTypeConfig:
    """
    Parse and validate a single asset_type configuration dict (already
    loaded from YAML) into an AssetTypeConfig. Raises AssetTypeConfigError
    with a clear message on any structural problem.
    """

    _validate_raw_config(raw, source_path)

    fields = [
        FieldMapping(source=f["source"], target=f["target"], type=f["type"])
        for f in raw["fields"]
    ]

    return AssetTypeConfig(
        asset_type=raw["asset_type"],
        silver_table=raw["silver_table"],
        fields=fields,
        primary_key=raw.get("primary_key", ["event_id"]),
        deduplicate=bool(raw.get("deduplicate", True)),
    )


def load_asset_type_config(asset_type: str, asset_types_dir: str | None = None) -> AssetTypeConfig:
    """
    Load and validate config/asset_types/<asset_type>.yml.

    `asset_types_dir` defaults to resolve_asset_types_dir() when not
    given explicitly, so production DLT code (which never passes this
    argument) automatically picks up the pipeline-configuration-supplied
    directory, while tests/tooling may still pass an explicit directory.

    Raises AssetTypeConfigError (with a clear, actionable message) if the
    file is missing or malformed — per the requirement that a malformed
    configuration produce a clear error rather than fail silently.
    """

    asset_types_dir = asset_types_dir or resolve_asset_types_dir()
    path = os.path.join(asset_types_dir, f"{asset_type}.yml")

    if not os.path.exists(path):
        raise AssetTypeConfigError(
            f"No asset type configuration found for '{asset_type}' "
            f"(expected {path}). To onboard a new asset type, add "
            f"config/asset_types/{asset_type}.yml."
        )

    with open(path, "r", encoding="utf-8") as fh:
        try:
            raw = yaml.safe_load(fh)
        except yaml.YAMLError as exc:
            raise AssetTypeConfigError(
                f"Failed to parse YAML for asset type '{asset_type}' at "
                f"{path}: {exc}"
            ) from exc

    if raw is None:
        raise AssetTypeConfigError(
            f"Asset type configuration '{path}' is empty."
        )

    return parse_asset_type_config(raw, source_path=path)


def discover_asset_type_configs(asset_types_dir: str | None = None) -> list[AssetTypeConfig]:
    """
    Load and validate every config/asset_types/*.yml file found on disk.

    `asset_types_dir` defaults to resolve_asset_types_dir() when not
    given explicitly (see load_asset_type_config for why).

    This is what makes onboarding a new asset type purely config-driven:
    dropping a new <asset_type>.yml file into config/asset_types/ is
    automatically picked up here — no Python code changes required.
    """

    asset_types_dir = asset_types_dir or resolve_asset_types_dir()
    if not os.path.isdir(asset_types_dir):
        raise AssetTypeConfigError(
            f"Asset type config directory not found: {asset_types_dir}"
        )

    configs: list[AssetTypeConfig] = []
    for filename in sorted(os.listdir(asset_types_dir)):
        if not (filename.endswith(".yml") or filename.endswith(".yaml")):
            continue
        path = os.path.join(asset_types_dir, filename)
        with open(path, "r", encoding="utf-8") as fh:
            try:
                raw = yaml.safe_load(fh)
            except yaml.YAMLError as exc:
                raise AssetTypeConfigError(
                    f"Failed to parse YAML config '{path}': {exc}"
                ) from exc
        if raw is None:
            raise AssetTypeConfigError(f"Asset type configuration '{path}' is empty.")
        configs.append(parse_asset_type_config(raw, source_path=path))

    return configs
