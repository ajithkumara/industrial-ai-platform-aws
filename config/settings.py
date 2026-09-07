"""
Application configuration (AWS-native).

Loads configuration from the .env file and exposes a single immutable
settings object shared throughout the application.

AWS translation of the Azure reference (`config/settings.py`):
  Event Hubs  -> Amazon Kinesis Data Streams  (KinesisSettings)
  ADLS Gen2   -> Amazon S3                     (StorageSettings)
  Blob checkpoint / local file -> local file (dev) + DynamoDB lease (prod)
                                              (CheckpointSettings)

The NATS bridge settings are cloud-independent and are preserved unchanged
from the Azure reference.

This module has NO boto3 / AWS SDK import — it only parses environment
variables into frozen dataclasses, so importing it is cheap and side-effect
free (see the lazy-validation note at the bottom).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------
# Base paths
# ---------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

LOGS_DIR = BASE_DIR / "logs"
DATA_DIR = BASE_DIR / "data"

LOGS_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)

# Local-dev checkpoint file (production uses the DynamoDB lease table below).
CHECKPOINT_FILE = DATA_DIR / "checkpoints.json"
LOCAL_FALLBACK_DIR = DATA_DIR / "telemetry-data"

# ---------------------------------------------------------------------
# Configuration Models
# ---------------------------------------------------------------------


@dataclass(frozen=True)
class KinesisSettings:
    """Amazon Kinesis Data Streams — replaces Azure Event Hubs."""
    stream_name: str
    consumer_name: str  # KCL application name (owns the DynamoDB lease table)
    region: str


@dataclass(frozen=True)
class StorageSettings:
    """Amazon S3 — replaces ADLS Gen2."""
    bucket: str
    region: str
    raw_folder: str
    raw_batch_size: int


@dataclass(frozen=True)
class CheckpointSettings:
    """
    Consumer checkpoint store.

    Local development uses a JSON file (CHECKPOINT_FILE above). Production
    uses a DynamoDB lease table (the KCL-native mechanism) — never the local
    file. `table_name` is only required in production.
    """
    table_name: str
    region: str


@dataclass(frozen=True)
class NatsSettings:
    url: str
    bearing_sensor_subject: str
    bearing_inference_subject: str
    orchestrator_mode_subject: str
    context_snapshot_subject: str


@dataclass(frozen=True)
class AppSettings:
    kinesis: KinesisSettings
    storage: StorageSettings
    checkpoint: CheckpointSettings
    consumer_batch_size: int
    nats: NatsSettings


# ---------------------------------------------------------------------
# Build Settings Object
# ---------------------------------------------------------------------

settings = AppSettings(

    kinesis=KinesisSettings(
        stream_name=os.getenv("KINESIS_STREAM_NAME", ""),
        consumer_name=os.getenv("KINESIS_CONSUMER_NAME", "bronze-loader"),
        region=os.getenv("AWS_REGION", ""),
    ),

    storage=StorageSettings(
        bucket=os.getenv("S3_BUCKET", ""),
        region=os.getenv("AWS_REGION", ""),
        raw_folder=os.getenv("RAW_FOLDER", "raw/telemetry"),
        raw_batch_size=int(os.getenv("RAW_BATCH_SIZE", "20")),
    ),

    checkpoint=CheckpointSettings(
        # Empty in local dev (file checkpoint used); required in production.
        table_name=os.getenv("CHECKPOINT_TABLE", ""),
        region=os.getenv("AWS_REGION", ""),
    ),

    consumer_batch_size=int(os.getenv("CONSUMER_BATCH_SIZE", "20")),

    # NATS -> Kinesis bridge settings (edge/nats_bearing_bridge.py). Cloud
    # independent; preserved verbatim from the Azure reference. Subject names
    # remain UNVERIFIED against the real adaptive-edge-orchestrator repo —
    # see edge/nats_bearing_bridge.py's module docstring.
    nats=NatsSettings(
        url=os.getenv("NATS_URL", "nats://localhost:4222"),
        bearing_sensor_subject=os.getenv("NATS_BEARING_SENSOR_SUBJECT", "sensors.bearing"),
        bearing_inference_subject=os.getenv("NATS_BEARING_INFERENCE_SUBJECT", "inference.bearing"),
        orchestrator_mode_subject=os.getenv("NATS_ORCHESTRATOR_MODE_SUBJECT", "orchestrator.mode"),
        context_snapshot_subject=os.getenv("NATS_CONTEXT_SNAPSHOT_SUBJECT", "context.snapshot"),
    ),
)


# ---------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------


def validate_settings() -> None:
    """
    Validate all required application settings for the AWS runtime.

    Required for the consumer to run: a Kinesis stream to read, an S3 bucket
    to write, and an AWS region. The DynamoDB checkpoint table is only
    required in production and is validated by the production entry point, not
    here (local dev uses a file checkpoint).
    """

    missing = []

    if not settings.kinesis.stream_name:
        missing.append("KINESIS_STREAM_NAME")

    if not settings.storage.bucket:
        missing.append("S3_BUCKET")

    if not settings.storage.region:
        missing.append("AWS_REGION")

    if missing:
        raise ValueError(
            f"Missing configuration values: {', '.join(missing)}"
        )


# NOTE: validate_settings() is intentionally NOT called automatically at
# import time. This module is imported transitively by nearly every package
# (consumer/, edge/, tests/), including in CI where no real AWS resources are
# present. Importing config.settings must be side-effect free. Entry points
# that require fully-populated settings (the Kinesis consumer main(), the
# Kinesis producer __init__) call validate_settings() explicitly. This
# preserves the Azure reference's Phase-5 lazy-validation contract exactly.
