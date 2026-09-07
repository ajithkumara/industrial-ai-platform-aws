"""
Tests for edge/nats_bearing_bridge.py's pure translation logic
(translate_sensor_record / translate_inference_record).

Deliberately does NOT test NatsBearingBridge itself (requires a live NATS
connection + Event Hub credentials) -- only the translation functions,
which are pure and don't need either.

The two sample payloads below are exactly the examples the bridge was
built from. If the real adaptive-edge-orchestrator payloads differ, these
tests (and the config/asset_types/bearing_*.yml files) need updating —
see the caveats in edge/nats_bearing_bridge.py's module docstring.
"""

import json

from edge.nats_bearing_bridge import (
    NatsBearingBridge,
    translate_context_snapshot_record,
    translate_inference_record,
    translate_mode_transition_record,
    translate_sensor_record,
)
from shared.telemetry_event import TelemetryEvent

SAMPLE_SENSOR_RECORD = {
    "ts": "2026-08-01T14:32:07.812Z",
    "seq": 42,
    "sensor_id": "bearing.DE",
    "file": "ball_0hp.mat",
    "label": "inner_race",
    "window_idx": 17,
    "features": {
        "rms": 0.12,
        "peak": 0.45,
        "crest": 3.75,
        "kurtosis": 2.1,
        "skew": -0.3,
        "variance": 0.014,
        "mean_abs": 0.09,
    },
}

SAMPLE_INFERENCE_RECORD = {
    "ts": "2026-08-01T14:32:08.001Z",
    "seq": 42,
    "sensor_id": "bearing.DE",
    "label": "inner_race",
    "anomaly": True,
    "anomaly_score": 0.83,
    "infer_ms": 4.2,
    "mode": "EDGE_AUTONOMOUS",
    "stats": {
        "total": 1204,
        "anomalies": 37,
        "accuracy": 0.961,
        "elapsed_s": 118.4,
    },
}


def test_translate_sensor_record_produces_valid_envelope():
    event = translate_sensor_record(SAMPLE_SENSOR_RECORD)
    # Must satisfy the same generic envelope every other asset type uses.
    validated = TelemetryEvent.model_validate(event)
    assert validated.asset_type == "bearing_sensor"
    assert validated.device_id == "bearing.DE"
    assert validated.timestamp == SAMPLE_SENSOR_RECORD["ts"]
    assert validated.payload == SAMPLE_SENSOR_RECORD


def test_translate_sensor_record_priority_reflects_fault_label():
    normal = translate_sensor_record({**SAMPLE_SENSOR_RECORD, "label": "normal"})
    faulty = translate_sensor_record({**SAMPLE_SENSOR_RECORD, "label": "inner_race"})
    assert normal["priority"] == "normal"
    assert faulty["priority"] == "high"


def test_translate_inference_record_produces_valid_envelope():
    event = translate_inference_record(SAMPLE_INFERENCE_RECORD)
    validated = TelemetryEvent.model_validate(event)
    assert validated.asset_type == "bearing_inference"
    assert validated.device_id == "bearing.DE"
    assert validated.payload["mode"] == "EDGE_AUTONOMOUS"


def test_translate_inference_record_priority_reflects_anomaly_flag():
    normal = translate_inference_record({**SAMPLE_INFERENCE_RECORD, "anomaly": False})
    anomalous = translate_inference_record({**SAMPLE_INFERENCE_RECORD, "anomaly": True})
    assert normal["priority"] == "normal"
    assert anomalous["priority"] == "high"


def test_translate_is_deterministic_for_the_same_source_message():
    # Same source message translated twice (simulating NATS at-least-once
    # redelivery) must produce the same event_id, so Silver's
    # dedup-by-event_id logic collapses the duplicate instead of double
    # counting it.
    event_a = translate_sensor_record(SAMPLE_SENSOR_RECORD)
    event_b = translate_sensor_record(SAMPLE_SENSOR_RECORD)
    assert event_a["event_id"] == event_b["event_id"]


def test_translate_produces_different_ids_for_different_messages():
    event_a = translate_sensor_record(SAMPLE_SENSOR_RECORD)
    event_b = translate_sensor_record({**SAMPLE_SENSOR_RECORD, "seq": 43})
    assert event_a["event_id"] != event_b["event_id"]


def test_sensor_and_inference_ids_dont_collide_even_with_same_seq_and_sensor():
    # Same seq/sensor_id/ts could plausibly appear on both subjects for
    # the same underlying reading -- the `subject` argument keeps their
    # event_ids distinct.
    sensor_event = translate_sensor_record(SAMPLE_SENSOR_RECORD)
    inference_event = translate_inference_record(
        {**SAMPLE_INFERENCE_RECORD, "ts": SAMPLE_SENSOR_RECORD["ts"]}
    )
    assert sensor_event["event_id"] != inference_event["event_id"]


# ---------------------------------------------------------------------------
# orchestrator_mode -- the primary thesis evidence stream
# ---------------------------------------------------------------------------

SAMPLE_MODE_TRANSITION_RECORD = {
    "ts": "2026-08-01T14:32:07.812Z",
    "device_id": "edge-node-01",
    "from_mode": "CLOUD_OPTIMISED",
    "to_mode": "EDGE_ONLY",
    "trigger": "network",
    "rtt_ms": 992.0,
    "cpu_pct": 12.4,
    "edge_confidence": 0.58,
    "breach_count": 3,
    "policy_version": "policy-v1.2",
}


def test_translate_mode_transition_record_produces_valid_envelope():
    event = translate_mode_transition_record(SAMPLE_MODE_TRANSITION_RECORD)
    validated = TelemetryEvent.model_validate(event)
    assert validated.asset_type == "orchestrator_mode"
    assert validated.device_id == "edge-node-01"
    assert validated.priority == "high"
    assert validated.payload == SAMPLE_MODE_TRANSITION_RECORD


def test_translate_mode_transition_is_deterministic():
    event_a = translate_mode_transition_record(SAMPLE_MODE_TRANSITION_RECORD)
    event_b = translate_mode_transition_record(SAMPLE_MODE_TRANSITION_RECORD)
    assert event_a["event_id"] == event_b["event_id"]


def test_translate_mode_transition_differs_by_from_to_mode():
    # Two different transitions for the same device at the "same" moment
    # (e.g. recorded with identical timestamps in a test rig) must not
    # collide -- from_mode/to_mode are part of the id key.
    event_a = translate_mode_transition_record(SAMPLE_MODE_TRANSITION_RECORD)
    event_b = translate_mode_transition_record(
        {**SAMPLE_MODE_TRANSITION_RECORD, "to_mode": "EDGE_AUTONOMOUS"}
    )
    assert event_a["event_id"] != event_b["event_id"]


# ---------------------------------------------------------------------------
# context_snapshot
# ---------------------------------------------------------------------------

SAMPLE_CONTEXT_SNAPSHOT_RECORD = {
    "ts": "2026-08-01T14:32:07.812Z",
    "device_id": "edge-node-01",
    "rtt_ms": 992.0,
    "cpu_pct": 12.4,
    "ram_pct": 41.0,
    "cloud_reachable": True,
}


def test_translate_context_snapshot_record_produces_valid_envelope():
    event = translate_context_snapshot_record(SAMPLE_CONTEXT_SNAPSHOT_RECORD)
    validated = TelemetryEvent.model_validate(event)
    assert validated.asset_type == "context_snapshot"
    assert validated.device_id == "edge-node-01"
    assert validated.priority == "normal"


def test_translate_context_snapshot_stamps_is_breach_sample():
    heartbeat = translate_context_snapshot_record(
        SAMPLE_CONTEXT_SNAPSHOT_RECORD, is_breach_sample=False
    )
    breach = translate_context_snapshot_record(
        SAMPLE_CONTEXT_SNAPSHOT_RECORD, is_breach_sample=True
    )
    assert heartbeat["payload"]["is_breach_sample"] is False
    assert breach["payload"]["is_breach_sample"] is True
    # Original raw dict passed in must not be mutated by the translator.
    assert "is_breach_sample" not in SAMPLE_CONTEXT_SNAPSHOT_RECORD


# ---------------------------------------------------------------------------
# NatsBearingBridge context-snapshot sampling policy (breach + heartbeat
# only, not full 1Hz) -- exercised directly against the bridge's internal
# handler rather than a live NATS connection.
# ---------------------------------------------------------------------------


class _FakeMsg:
    def __init__(self, data: dict):
        self.data = json.dumps(data).encode()


class _RecordingProducer:
    """Stand-in for EventHubProducer that just records what was sent."""

    def __init__(self):
        self.sent: list[dict] = []

    def send_events(self, events):
        self.sent.extend(events)

    def close(self):
        pass


def _bridge_with_recording_producer() -> tuple[NatsBearingBridge, _RecordingProducer]:
    # Deliberately bypass __init__ (object.__new__) rather than calling
    # NatsBearingBridge(...) directly: the real constructor builds a real
    # EventHubProducer, which calls validate_settings() and requires
    # Azure credentials that aren't present in CI. _on_context_message
    # only touches _context_subject / _last_context_forward / _producer,
    # so those are all that need to be set up here.
    bridge = object.__new__(NatsBearingBridge)
    bridge._context_subject = "context.snapshot"
    bridge._last_context_forward = {}
    recorder = _RecordingProducer()
    bridge._producer = recorder
    return bridge, recorder


async def _drive(coro):
    return await coro


def test_context_sampling_forwards_breach_samples_immediately():
    import asyncio

    bridge, recorder = _bridge_with_recording_producer()
    msg = _FakeMsg({**SAMPLE_CONTEXT_SNAPSHOT_RECORD, "breach": True})
    asyncio.run(_drive(bridge._on_context_message(msg)))
    assert len(recorder.sent) == 1
    assert recorder.sent[0]["payload"]["is_breach_sample"] is True


def test_context_sampling_drops_non_breach_samples_within_heartbeat_window():
    import asyncio

    bridge, recorder = _bridge_with_recording_producer()
    msg = _FakeMsg(SAMPLE_CONTEXT_SNAPSHOT_RECORD)
    # First non-breach sample for a device is always forwarded (no prior
    # heartbeat recorded yet -> due immediately).
    asyncio.run(_drive(bridge._on_context_message(msg)))
    assert len(recorder.sent) == 1
    # A second non-breach sample immediately after must be dropped -- not
    # yet 30s since the last forward.
    asyncio.run(_drive(bridge._on_context_message(msg)))
    assert len(recorder.sent) == 1
