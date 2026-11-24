"""
S3 Direct Writer for MP91 Telemetry
====================================
Writes parsed telemetry events directly to S3 as JSONL files,
partitioned by year/month/day — same layout as the generated
telemetry data already queryable by Athena.

Used when Kinesis is not running (e.g. dev/cost-saving mode).
Set S3_BUCKET env var to enable; falls back to stdout if not set.

Partition layout:
  s3://<bucket>/raw/telemetry/year=YYYY/month=MM/day=DD/mp91_<ts>.jsonl

Author: Ajith Kumara
Project: Industrial AI Platform (AWS) — Edge
"""

from __future__ import annotations

import io
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger("mp91_s3_writer")

UTC = timezone.utc

# ── config ────────────────────────────────────────────────────────────────────
S3_BUCKET: Optional[str] = os.environ.get("S3_BUCKET")
S3_PREFIX: str = os.environ.get("S3_PREFIX", "raw/telemetry")
AWS_REGION: str = os.environ.get("AWS_DEFAULT_REGION", "ca-central-1")

# Buffer events and flush to S3 every FLUSH_INTERVAL_S seconds (reduces API calls)
FLUSH_INTERVAL_S: int = int(os.environ.get("S3_FLUSH_INTERVAL_S", "30"))


class S3Writer:
    """
    Thread-safe buffered S3 JSONL writer.
    Accumulates events in memory and flushes on interval or buffer size.
    """

    def __init__(self, bucket: str, prefix: str = S3_PREFIX, region: str = AWS_REGION):
        import boto3
        self._s3 = boto3.client("s3", region_name=region)
        self._bucket = bucket
        self._prefix = prefix
        self._buffer: list[dict] = []
        self._lock = threading.Lock()
        self._last_flush = time.time()

        # Start background flush thread
        self._flush_thread = threading.Thread(
            target=self._flush_loop,
            name="s3-flush",
            daemon=True,
        )
        self._flush_thread.start()
        log.info("S3Writer initialised — bucket=%s  prefix=%s", bucket, prefix)

    def write(self, event: dict) -> None:
        """Add event to buffer; flushes automatically in background."""
        with self._lock:
            self._buffer.append(event)

    def flush(self) -> None:
        """Flush buffered events to S3 immediately."""
        with self._lock:
            if not self._buffer:
                return
            batch = self._buffer[:]
            self._buffer.clear()

        now = datetime.now(UTC)
        key = (
            f"{self._prefix}/"
            f"year={now.strftime('%Y')}/"
            f"month={now.strftime('%m')}/"
            f"day={now.strftime('%d')}/"
            f"mp91_{now.strftime('%Y%m%dT%H%M%SZ')}_{len(batch)}events.jsonl"
        )

        body = "\n".join(json.dumps(e) for e in batch) + "\n"
        try:
            self._s3.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=body.encode("utf-8"),
                ContentType="application/x-ndjson",
            )
            log.info("S3 flush: %d events → s3://%s/%s", len(batch), self._bucket, key)
        except Exception as exc:
            log.error("S3 flush failed: %s — %d events lost", exc, len(batch))

    def _flush_loop(self) -> None:
        """Background thread: flush every FLUSH_INTERVAL_S seconds."""
        while True:
            time.sleep(FLUSH_INTERVAL_S)
            try:
                self.flush()
            except Exception as exc:
                log.error("Background flush error: %s", exc)


# ── module-level singleton ────────────────────────────────────────────────────

_writer: Optional[S3Writer] = None
_writer_lock = threading.Lock()


def get_writer() -> Optional[S3Writer]:
    """Return the module-level S3Writer singleton, or None if S3_BUCKET not set."""
    global _writer
    if _writer is not None:
        return _writer
    if not S3_BUCKET:
        return None
    with _writer_lock:
        if _writer is None:
            _writer = S3Writer(S3_BUCKET)
    return _writer


def write_event(event: dict) -> None:
    """Write a single event. Falls back to log if S3 not configured."""
    writer = get_writer()
    if writer:
        writer.write(event)
    else:
        log.info("S3_BUCKET not set — event: %s", json.dumps(event))


def flush() -> None:
    """Flush any buffered events immediately (call on shutdown)."""
    writer = get_writer()
    if writer:
        writer.flush()
