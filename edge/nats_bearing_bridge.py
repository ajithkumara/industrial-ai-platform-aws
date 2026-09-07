"""
NATS -> Event Hub Bridge for bearing sensor / inference telemetry.

Brings adaptive-edge-orchestrator's bearing-fault-classification events
(published to NATS by sensor_replay.py, inference_engine.py, the Policy
Executor, and the Context Monitor) into this platform's generic
TelemetryEvent envelope, so they flow through the exact same Event Hub ->
consumer -> ADLS -> DLT Bronze/Silver/Gold pipeline as vehicle/industrial
telemetry -- via four config-driven asset types: bearing_sensor,
bearing_inference, orchestrator_mode, and context_snapshot (see
config/asset_types/). A fifth asset type, cloud_validation, shares this
pipeline but is produced cloud-side by the CloudForest scoring job, not
bridged from NATS -- see config/asset_types/cloud_validation.yml.

This module intentionally does NOT reimplement any edge decisioning logic.
adaptive-edge-orchestrator already owns the ultra-low-latency
edge-autonomous inference loop; this bridge's only job is forwarding the
resulting records for downstream analysis/research. The edge model's
decision is always final and is never blocked, delayed, or overridden by
anything this bridge or the cloud side does -- HYBRID-mode cloud
validation is asynchronous enrichment recorded after the fact.

IMPORTANT -- built without access to the adaptive-edge-orchestrator repo,
from pasted payload examples only. Verify against the real
sensor_replay.py / inference_engine.py publish calls before relying on
this in production:
  - Exact NATS subject names (bearing_sensor_subject / NATS_BEARING_SENSOR_SUBJECT
    was stated as "sensors.bearing"; bearing_inference_subject /
    NATS_BEARING_INFERENCE_SUBJECT is an unverified guess,
    "inference.bearing").
  - Whether `ts` is always a valid ISO-8601 string (assumed here).
  - Whether any of the fields below can be missing/null in practice --
    translate_sensor_record/translate_inference_record currently assume
    all documented fields are always present and will raise KeyError if
    not (fail loud rather than silently drop data, consistent with this
    repo's "malformed input should fail clearly" convention elsewhere).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any

logger = logging.getLogger(__name__)

# Fixed namespace for deriving deterministic event_ids via uuid5, so that
# NATS at-least-once redelivery of the same source message maps to the
# same event_id every time -- Silver's deduplicate-by-event_id logic
# (dlt/silver/clean_and_deduplicate.py) then collapses redelivered
# duplicates instead of double-counting them. Value is arbitrary but must
# stay constant.
_BRIDGE_NAMESPACE = uuid.UUID("6f1b3c2a-6e6a-4b1a-9a7a-2b8f6b8b8a2e")

SCHEMA_VERSION = "1.0.0"


def _deterministic_event_id(*parts: Any) -> str:
    key = ":".join(str(p) for p in parts)
    return str(uuid.uuid5(_BRIDGE_NAMESPACE, key))


def translate_sensor_record(raw: dict, subject: str = "sensors.bearing") -> dict:
    """
    Translate a raw NATS "Sensor Record" (published by
    adaptive-edge-orchestrator's sensor_replay.py) into a TelemetryEvent-
    shaped dict with asset_type="bearing_sensor".

    Expected raw shape (see module docstring for the verification caveat):
        {
          "ts": "2026-08-01T14:32:07.812Z",
          "seq": 42,
          "sensor_id": "bearing.DE",
          "file": "ball_0hp.mat",
          "label": "inner_race",
          "window_idx": 17,
          "features": {"rms": ..., "peak": ..., "crest": ..., "kurtosis": ...,
                       "skew": ..., "variance": ..., "mean_abs": ...}
        }
    """

    label = raw["label"]
    priority = "high" if label != "normal" else "normal"

    return {
        "event_id": _deterministic_event_id(subject, raw["sensor_id"], raw["seq"], raw["ts"]),
        "device_id": raw["sensor_id"],
        "asset_type": "bearing_sensor",
        "timestamp": raw["ts"],
        "priority": priority,
        "schema_version": SCHEMA_VERSION,
        "payload": raw,
    }


def translate_mode_transition_record(raw: dict, subject: str = "orchestrator.mode") -> dict:
    """
    Translate a raw NATS "Mode Transition Record" (published by
    adaptive-edge-orchestrator's Policy Executor whenever the
    orchestrator changes mode) into a TelemetryEvent-shaped dict with
    asset_type="orchestrator_mode".

    This is the primary thesis evidence stream -- see
    config/asset_types/orchestrator_mode.yml.

    Expected raw shape (see module docstring for the verification
    caveat):
        {
          "ts": "2026-08-01T14:32:07.812Z",
          "device_id": "edge-node-01",
          "from_mode": "CLOUD_OPTIMISED",
          "to_mode": "EDGE_ONLY",
          "trigger": "network",
          "rtt_ms": 992.0,
          "cpu_pct": 12.4,
          "edge_confidence": 0.58,
          "breach_count": 3,
          "policy_version": "policy-v1.2"
        }
    """

    return {
        "event_id": _deterministic_event_id(
            subject, raw["device_id"], raw["from_mode"], raw["to_mode"], raw["ts"]
        ),
        "device_id": raw["device_id"],
        "asset_type": "orchestrator_mode",
        "timestamp": raw["ts"],
        "priority": "high",
        "schema_version": SCHEMA_VERSION,
        "payload": raw,
    }


def translate_context_snapshot_record(
    raw: dict, subject: str = "context.snapshot", is_breach_sample: bool = False
) -> dict:
    """
    Translate a raw NATS "Context Snapshot Record" (published by
    adaptive-edge-orchestrator's Context Monitor at ~1Hz) into a
    TelemetryEvent-shaped dict with asset_type="context_snapshot".

    NatsBearingBridge does NOT forward every 1Hz sample -- see
    config/asset_types/context_snapshot.yml. `is_breach_sample` is
    stamped onto the payload so downstream Gold queries can distinguish
    "this sample caused a mode-switch decision" from "this is a
    background heartbeat proving continuous monitoring."

    Expected raw shape (see module docstring for the verification
    caveat):
        {
          "ts": "2026-08-01T14:32:07.812Z",
          "device_id": "edge-node-01",
          "rtt_ms": 992.0,
          "cpu_pct": 12.4,
          "ram_pct": 41.0,
          "cloud_reachable": true
        }
    """

    payload = dict(raw)
    payload["is_breach_sample"] = is_breach_sample

    return {
        "event_id": _deterministic_event_id(subject, raw["device_id"], raw["ts"]),
        "device_id": raw["device_id"],
        "asset_type": "context_snapshot",
        "timestamp": raw["ts"],
        "priority": "normal",
        "schema_version": SCHEMA_VERSION,
        "payload": payload,
    }


def translate_inference_record(raw: dict, subject: str = "inference.bearing") -> dict:
    """
    Translate a raw NATS "Inference Result Record" (published by
    adaptive-edge-orchestrator's inference_engine.py) into a
    TelemetryEvent-shaped dict with asset_type="bearing_inference".

    Expected raw shape (see module docstring for the verification caveat):
        {
          "ts": "2026-08-01T14:32:08.001Z",
          "seq": 42,
          "sensor_id": "bearing.DE",
          "label": "inner_race",
          "anomaly": true,
          "anomaly_score": 0.83,
          "infer_ms": 4.2,
          "mode": "EDGE_AUTONOMOUS",
          "stats": {"total": ..., "anomalies": ..., "accuracy": ..., "elapsed_s": ...}
        }
    """

    priority = "high" if raw["anomaly"] else "normal"

    return {
        "event_id": _deterministic_event_id(subject, raw["sensor_id"], raw["seq"], raw["ts"]),
        "device_id": raw["sensor_id"],
        "asset_type": "bearing_inference",
        "timestamp": raw["ts"],
        "priority": priority,
        "schema_version": SCHEMA_VERSION,
        "payload": raw,
    }


class NatsBearingBridge:
    """
    Subscribes to the configured NATS subjects and republishes translated
    events onto Event Hub via the existing EventHubProducer -- no new
    Event Hub client code, reuses exactly what edge/vehicle_producer.py
    and edge/industrial_producer.py already use.

    A malformed/unexpected message on either subject is logged and
    skipped rather than crashing the bridge, so one bad message from the
    thesis rig doesn't take down the whole bridge process.
    """

    # Minimum gap between forwarded context.snapshot heartbeat samples per
    # device, when the sample isn't itself a breach. Keeps the 1Hz local
    # stream from becoming a 1Hz cloud stream while still proving
    # continuous monitoring in the archive.
    _CONTEXT_HEARTBEAT_INTERVAL_S = 30.0

    def __init__(
        self,
        nats_url: str,
        sensor_subject: str,
        inference_subject: str,
        mode_subject: str = "orchestrator.mode",
        context_subject: str = "context.snapshot",
    ):
        self._nats_url = nats_url
        self._sensor_subject = sensor_subject
        self._inference_subject = inference_subject
        self._mode_subject = mode_subject
        self._context_subject = context_subject
        # Lazy import: the concrete Kinesis producer lives in
        # edge/base_producer.py (Milestone 2). Importing it lazily keeps
        # the pure translate_* functions in this module importable with no
        # cloud SDK present (used by data-quality tests + fixtures).
        from .base_producer import EventHubProducer

        self._producer = EventHubProducer()
        self._nc = None
        self._last_context_forward: dict[str, float] = {}

    async def _on_sensor_message(self, msg) -> None:
        try:
            raw = json.loads(msg.data.decode())
            event = translate_sensor_record(raw, subject=self._sensor_subject)
        except Exception:
            logger.exception(
                "Failed to translate sensor record from subject '%s'; skipping.",
                self._sensor_subject,
            )
            return
        self._producer.send_events([event])

    async def _on_inference_message(self, msg) -> None:
        try:
            raw = json.loads(msg.data.decode())
            event = translate_inference_record(raw, subject=self._inference_subject)
        except Exception:
            logger.exception(
                "Failed to translate inference record from subject '%s'; skipping.",
                self._inference_subject,
            )
            return
        self._producer.send_events([event])

    async def _on_mode_message(self, msg) -> None:
        # Mode transitions are rare and are the primary thesis evidence
        # stream -- always forward, no sampling.
        try:
            raw = json.loads(msg.data.decode())
            event = translate_mode_transition_record(raw, subject=self._mode_subject)
        except Exception:
            logger.exception(
                "Failed to translate mode transition record from subject '%s'; skipping.",
                self._mode_subject,
            )
            return
        self._producer.send_events([event])

    async def _on_context_message(self, msg) -> None:
        try:
            raw = json.loads(msg.data.decode())
        except Exception:
            logger.exception(
                "Failed to parse context snapshot from subject '%s'; skipping.",
                self._context_subject,
            )
            return

        # Forward if this sample itself signals a breach (as reported by
        # the orchestrator), or if enough time has passed since the last
        # forwarded sample for this device (heartbeat). Everything else
        # is dropped -- it stays in the local JSONL log per the
        # three-tier retention design, it just doesn't need to also be
        # in the cloud archive at full 1Hz resolution.
        device_id = raw.get("device_id", "unknown")
        is_breach = bool(raw.get("breach", False))
        now = time.monotonic()
        last_forward = self._last_context_forward.get(device_id, 0.0)
        is_heartbeat_due = (now - last_forward) >= self._CONTEXT_HEARTBEAT_INTERVAL_S

        if not (is_breach or is_heartbeat_due):
            return

        try:
            event = translate_context_snapshot_record(
                raw, subject=self._context_subject, is_breach_sample=is_breach
            )
        except Exception:
            logger.exception(
                "Failed to translate context snapshot from subject '%s'; skipping.",
                self._context_subject,
            )
            return

        self._last_context_forward[device_id] = now
        self._producer.send_events([event])

    async def run(self) -> None:
        # Imported lazily so `nats-py` is only required when the bridge is
        # actually used, not for every consumer/edge import in the repo.
        import nats

        self._nc = await nats.connect(self._nats_url)
        logger.info("Connected to NATS at %s", self._nats_url)

        await self._nc.subscribe(self._sensor_subject, cb=self._on_sensor_message)
        await self._nc.subscribe(self._inference_subject, cb=self._on_inference_message)
        await self._nc.subscribe(self._mode_subject, cb=self._on_mode_message)
        await self._nc.subscribe(self._context_subject, cb=self._on_context_message)
        logger.info(
            "Subscribed to '%s', '%s', '%s', and '%s'.",
            self._sensor_subject,
            self._inference_subject,
            self._mode_subject,
            self._context_subject,
        )

        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            await self.close()

    async def close(self) -> None:
        if self._nc is not None:
            await self._nc.drain()
        self._producer.close()
