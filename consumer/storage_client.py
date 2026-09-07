"""
Amazon S3 Storage Client

Handles uploading raw telemetry batches to Amazon S3 (the AWS raw/Bronze
landing zone). AWS-native translation of the Azure reference
`consumer/storage_client.py` (ADLS Gen2 DataLakeServiceClient).

The LOGICAL contract is preserved exactly:
  - JSONL batch files under raw/telemetry/year=/month=/day=/telemetry_<ts>_<uuid8>.jsonl
  - single-object DLQ records under raw/telemetry/_dlq/year=/month=/day=/dlq_<ts>_<uuid8>.json
  - deterministic, date-partitioned key layout
  - idempotent writes (each object key is unique via uuid8; overwrite-safe)

Only the transport changes (S3 PutObject via boto3 instead of ADLS
upload_data). S3 has no directories, so the Azure client's _ensure_directory
step is intentionally dropped — S3 keys are flat and created on write.

Author: Ajith Kumara
Project: Industrial AI Platform (AWS)
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
UTC = timezone.utc  # compat: datetime.UTC was added in Python 3.11
from pathlib import PurePosixPath
from typing import Final

import boto3

from config.settings import settings

logger = logging.getLogger(__name__)


class StorageClient:
    """
    Amazon S3 raw-landing client.

    Responsibilities
    ----------------
    - Connect to S3
    - Convert telemetry into JSONL
    - Upload telemetry batches to the raw/Bronze prefix
    - Write rejected events to the DLQ prefix

    Does NOT
    --------
    - Read Kinesis
    - Manage checkpoints
    - Validate telemetry records
    """

    def __init__(self, s3_client=None) -> None:
        self.bucket: str = settings.storage.bucket
        self.raw_folder: str = settings.storage.raw_folder
        self.dlq_folder: str = f"{self.raw_folder}/_dlq"

        logger.info("Connecting to S3 bucket '%s'...", self.bucket)

        # Injectable for tests (moto). In production the client is built from
        # the ambient IAM role / region — no static credentials.
        self._s3 = s3_client or boto3.client("s3", region_name=settings.storage.region)

        logger.info("Connected to S3 bucket '%s'.", self.bucket)

    # ----------------------------------------------------------

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(UTC)

    # ----------------------------------------------------------

    def _build_directory(self, base_folder: str | None = None) -> str:
        now = self._utc_now()
        folder = base_folder if base_folder is not None else self.raw_folder
        return str(
            PurePosixPath(
                folder,
                f"year={now.year}",
                f"month={now.month:02}",
                f"day={now.day:02}",
            )
        )

    # ----------------------------------------------------------

    def _build_filename(self, prefix: str = "telemetry", ext: str = "jsonl") -> str:
        now = self._utc_now()
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        unique = uuid.uuid4().hex[:8]
        return f"{prefix}_{timestamp}_{unique}.{ext}"

    # ----------------------------------------------------------

    @staticmethod
    def _events_to_jsonl(events: list[dict]) -> bytes:
        lines = [
            json.dumps(event, separators=(",", ":"), ensure_ascii=False)
            for event in events
        ]
        return ("\n".join(lines)).encode("utf-8")

    # ----------------------------------------------------------

    def upload_batch(self, events: list[dict]) -> str:
        """
        Upload a telemetry batch to the S3 raw/Bronze prefix as one JSONL
        object. Returns the S3 key written.

        Raises ValueError on an empty batch (same as the Azure reference), so
        BatchBuffer never issues a no-op write + checkpoint.
        """
        if not events:
            raise ValueError("Telemetry batch is empty.")

        directory = self._build_directory(self.raw_folder)
        filename = self._build_filename(prefix="telemetry", ext="jsonl")
        key = str(PurePosixPath(directory, filename))

        logger.info("Uploading %d telemetry event(s) to s3://%s/%s ...",
                    len(events), self.bucket, key)

        self._s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=self._events_to_jsonl(events),
            ContentType="application/x-ndjson",
        )

        logger.info("Successfully uploaded '%s'", key)
        return key

    # ----------------------------------------------------------

    def write_to_dlq(self, raw_body: str, error_reason: str) -> str:
        """
        Write a failed / invalid event to the Dead Letter Queue prefix.

        The DLQ lives at ``<raw_folder>/_dlq/year=.../month=.../day=.../`` so
        it is partitioned identically to the main raw data but physically
        isolated for discovery and replay. Each DLQ object is a single JSON
        record: {raw_body, error_reason, dlq_timestamp}.
        """
        directory = self._build_directory(self.dlq_folder)
        filename = self._build_filename(prefix="dlq", ext="json")
        key = str(PurePosixPath(directory, filename))

        dlq_record = json.dumps(
            {
                "raw_body": raw_body,
                "error_reason": error_reason,
                "dlq_timestamp": self._utc_now().isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")

        logger.warning("Writing rejected event to DLQ: 's3://%s/%s' | Reason: %s",
                       self.bucket, key, error_reason)

        self._s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=dlq_record,
            ContentType="application/json",
        )

        logger.info("DLQ event written to '%s'", key)
        return key
