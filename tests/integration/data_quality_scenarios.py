"""
Silver data-quality scenarios — proves the Bronze/Silver/Gold contracts hold
under deliberately bad input, before any ML work depends on them.

    Bronze = raw evidence (everything that survives the consumer lands here,
             duplicates included, unmodified)
    Silver = canonical / validated (deduplicated, envelope-clean, typed)
    Gold   = analysis-ready

The platform has THREE distinct quality gates, and a useful test must state
which gate is expected to catch each defect. Conflating them hides real
holes -- for example, a defect that "gets rejected" may in fact be silently
passing gate 1 and gate 2 and only failing at gate 3 as a NULL column.

  GATE 1 -- Consumer envelope validation (consumer/eventhub_consumer.py)
      Pydantic TelemetryEvent with model_config = {"extra": "forbid"}.
      Rejected events go to the DLQ at <raw_folder>/_dlq/ and NEVER reach
      Bronze. Catches: invalid JSON, missing required envelope fields,
      unexpected extra envelope fields, wrong envelope field types.

  GATE 2 -- Silver DLT expectations (dlt/silver/clean_and_deduplicate.py)
      @dlt.expect_or_drop on event_id / device_id / asset_type / timestamp
      being NOT NULL. Operates on data that already reached Bronze. Note
      that `timestamp` is passed through to_timestamp(), so an unparseable
      timestamp string becomes NULL here and is dropped at this gate even
      though it passed gate 1 as a valid string.

  GATE 3 -- Silver config-driven flatten (dlt/silver/flatten_payloads.py)
      Schema-aware field resolution. A configured payload field that is
      absent from the observed schema, or present but uncastable to its
      declared type, becomes a typed NULL column rather than failing the
      pipeline. An asset_type with no config/asset_types/*.yml produces no
      flattened table at all, while still appearing in
      cleaned_telemetry_events.

Each scenario below returns (events, expected) where `expected` names the
gate and the expected presence/absence at each layer, so the verification
queries assert something specific rather than "it didn't crash".

NOTE: events here are deliberately malformed. EventHubProducer.send_events()
performs no validation (it only serialises), so malformed dicts can be sent
exactly as constructed -- validation is the consumer's job, which is
precisely what these scenarios exercise.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from edge.nats_bearing_bridge import translate_sensor_record

# Distinct namespace so data-quality events can never collide with the
# functional scenarios in generate_bearing_events.py.
_DQ_NAMESPACE = uuid.UUID("b7c1d2e3-4f5a-6b7c-8d9e-0a1b2c3d4e5f")

_BASE_TS = datetime(2026, 8, 12, 12, 0, 0, tzinfo=timezone.utc)


def _ts(offset_seconds: float = 0.0) -> str:
    return (_BASE_TS + timedelta(seconds=offset_seconds)).strftime(
        "%Y-%m-%dT%H:%M:%S.%f"
    )[:-3] + "Z"


def _dq_id(tag: str) -> str:
    return str(uuid.uuid5(_DQ_NAMESPACE, tag))


def _well_formed_sensor(tag: str, offset: float = 0.0) -> dict:
    """A known-good bearing_sensor event used as the basis for mutations."""
    raw = {
        "ts": _ts(offset),
        "seq": 9000,
        "sensor_id": "bearing.DQ",
        "file": "normal_0hp.mat",
        "label": "normal",
        "window_idx": 1,
        "features": {
            "rms": 0.031, "peak": 0.092, "crest": 2.97, "kurtosis": 1.81,
            "skew": 0.02, "variance": 0.00096, "mean_abs": 0.024,
        },
    }
    event = translate_sensor_record(raw)
    event["event_id"] = _dq_id(tag)  # stable, scenario-scoped id
    return event


# ---------------------------------------------------------------------------
# DQ1 — valid control. Must survive all three gates untouched.
# ---------------------------------------------------------------------------
def dq1_valid_control():
    event = _well_formed_sensor("dq1-valid")
    return [event], {
        "scenario": "DQ1_valid_control",
        "event_ids": [event["event_id"]],
        "expected_gate": None,
        "in_dlq": False,
        "bronze_rows": 1,
        "cleaned_rows": 1,
        "flattened_rows": 1,
        "note": "Control. If this fails, the pipeline is broken, not the input.",
    }


# ---------------------------------------------------------------------------
# DQ2 — duplicate delivery. Bronze retains both; Silver collapses to one.
# ---------------------------------------------------------------------------
def dq2_duplicate_event():
    event = _well_formed_sensor("dq2-duplicate")
    return [event, dict(event)], {
        "scenario": "DQ2_duplicate_event",
        "event_ids": [event["event_id"]],
        "expected_gate": None,
        "in_dlq": False,
        "bronze_rows": 2,
        "cleaned_rows": 1,
        "flattened_rows": 1,
        "note": "Proves Bronze immutability AND Silver dedup in one scenario.",
    }


# ---------------------------------------------------------------------------
# DQ3 — missing required envelope field. GATE 1.
# ---------------------------------------------------------------------------
def dq3_missing_envelope_field():
    event = _well_formed_sensor("dq3-missing-field")
    marker = event["event_id"]
    del event["event_id"]
    return [event], {
        "scenario": "DQ3_missing_envelope_field",
        "event_ids": [marker],  # for reference only; never lands
        "expected_gate": "GATE 1 (consumer Pydantic — missing event_id)",
        "in_dlq": True,
        "bronze_rows": 0,
        "cleaned_rows": 0,
        "flattened_rows": 0,
    }


# ---------------------------------------------------------------------------
# DQ4 — unexpected extra envelope field. GATE 1 (extra="forbid").
# ---------------------------------------------------------------------------
def dq4_extra_envelope_field():
    event = _well_formed_sensor("dq4-extra-field")
    event["unexpected_field"] = "should be rejected"
    return [event], {
        "scenario": "DQ4_extra_envelope_field",
        "event_ids": [event["event_id"]],
        "expected_gate": "GATE 1 (consumer Pydantic — extra='forbid')",
        "in_dlq": True,
        "bronze_rows": 0,
        "cleaned_rows": 0,
        "flattened_rows": 0,
        "note": (
            "Confirms the envelope is a closed contract. If this lands in "
            "Bronze, extra='forbid' has been weakened and schema drift can "
            "enter the platform silently."
        ),
    }


# ---------------------------------------------------------------------------
# DQ5 — wrong envelope field type (payload as a string, not an object). GATE 1.
# ---------------------------------------------------------------------------
def dq5_wrong_envelope_type():
    event = _well_formed_sensor("dq5-wrong-type")
    event["payload"] = "this should be an object"
    return [event], {
        "scenario": "DQ5_wrong_envelope_type",
        "event_ids": [event["event_id"]],
        "expected_gate": "GATE 1 (consumer Pydantic — payload must be a mapping)",
        "in_dlq": True,
        "bronze_rows": 0,
        "cleaned_rows": 0,
        "flattened_rows": 0,
    }


# ---------------------------------------------------------------------------
# DQ6 — empty-string event_id. KNOWN GAP: passes gate 1 AND gate 2.
# ---------------------------------------------------------------------------
def dq6_empty_event_id():
    event = _well_formed_sensor("dq6-empty-id")
    event["event_id"] = ""
    return [event], {
        "scenario": "DQ6_empty_event_id",
        "event_ids": [""],
        "expected_gate": "GATE 1 (consumer Pydantic — min_length=1 on event_id)",
        "in_dlq": True,
        "bronze_rows": 0,
        "cleaned_rows": 0,
        "flattened_rows": 0,
        "note": (
            "REGRESSION GUARD for a defect this suite found and that has "
            "since been fixed. Previously an empty string was a valid `str` "
            "to Pydantic (gate 1 passed) and was NOT NULL to Spark (gate 2 "
            "passed), so the event reached Silver with a meaningless primary "
            "key shared by every such event — causing dedup-by-event_id to "
            "collapse unrelated events into one row. Fixed with defence in "
            "depth: min_length=1 on the identity fields of "
            "shared/telemetry_event.py (rejects at the consumer, so it never "
            "reaches Bronze), plus TRIM(event_id) <> '' in the Silver "
            "expectations of dlt/silver/clean_and_deduplicate.py (catches "
            "anything reaching Bronze by another route such as backfill or "
            "replay)."
        ),
    }


# ---------------------------------------------------------------------------
# DQ7 — unparseable timestamp. Passes gate 1, dropped at GATE 2.
# ---------------------------------------------------------------------------
def dq7_unparseable_timestamp():
    event = _well_formed_sensor("dq7-bad-timestamp")
    event["timestamp"] = "not-a-real-timestamp"
    return [event], {
        "scenario": "DQ7_unparseable_timestamp",
        "event_ids": [event["event_id"]],
        "expected_gate": "GATE 2 (to_timestamp -> NULL, expect_or_drop valid_timestamp)",
        "in_dlq": False,
        "bronze_rows": 1,
        "cleaned_rows": 0,
        "flattened_rows": 0,
        "note": (
            "Demonstrates the layered design working as intended: Bronze "
            "retains the raw evidence for audit, Silver refuses to publish "
            "it as canonical."
        ),
    }


# ---------------------------------------------------------------------------
# DQ8 — unknown asset_type. Passes gates 1 and 2; no flattened table (GATE 3).
# ---------------------------------------------------------------------------
def dq8_unknown_asset_type():
    event = _well_formed_sensor("dq8-unknown-type")
    event["asset_type"] = "mystery_sensor"
    return [event], {
        "scenario": "DQ8_unknown_asset_type",
        "event_ids": [event["event_id"]],
        "expected_gate": "GATE 3 (no config/asset_types/mystery_sensor.yml)",
        "in_dlq": False,
        "bronze_rows": 1,
        "cleaned_rows": 1,
        "flattened_rows": 0,
        "note": (
            "Proves an unmodelled domain degrades gracefully: the event is "
            "retained and queryable in the generic Silver table, it simply "
            "produces no domain-specific table. It must NOT fail the "
            "pipeline update."
        ),
    }


# ---------------------------------------------------------------------------
# DQ9 — payload missing a configured field. GATE 3 -> typed NULL.
# ---------------------------------------------------------------------------
def dq9_missing_payload_field():
    event = _well_formed_sensor("dq9-missing-payload-field")
    del event["payload"]["features"]["rms"]
    return [event], {
        "scenario": "DQ9_missing_payload_field",
        "event_ids": [event["event_id"]],
        "expected_gate": "GATE 3 (schema-aware fallback -> NULL rms)",
        "in_dlq": False,
        "bronze_rows": 1,
        "cleaned_rows": 1,
        "flattened_rows": 1,
        "expect_null_columns": ["rms"],
        "note": (
            "Partial data is preserved rather than discarded. Directly "
            "relevant to ML readiness: gold.bearing_ml_features must "
            "exclude or impute such rows explicitly, not inherit NULLs "
            "silently into training."
        ),
    }


# ---------------------------------------------------------------------------
# DQ10 — payload field present but uncastable. GATE 3 -> typed NULL.
# ---------------------------------------------------------------------------
def dq10_wrong_payload_type():
    event = _well_formed_sensor("dq10-wrong-payload-type")
    event["payload"]["features"]["kurtosis"] = "very high"
    return [event], {
        "scenario": "DQ10_wrong_payload_type",
        "event_ids": [event["event_id"]],
        "expected_gate": "GATE 3 (cast failure -> NULL kurtosis)",
        "in_dlq": False,
        "bronze_rows": 1,
        "cleaned_rows": 1,
        "flattened_rows": 1,
        "expect_null_columns": ["kurtosis"],
        "note": (
            "Spark's cast() yields NULL rather than raising, so a type "
            "error is indistinguishable from a missing value downstream. "
            "This is the single strongest argument for the ML feature "
            "table applying an explicit NOT NULL contract on every feature "
            "column rather than trusting Silver."
        ),
    }


# ---------------------------------------------------------------------------
# DQ11 — late-arriving event (event time far behind ingestion time).
# ---------------------------------------------------------------------------
def dq11_late_event():
    event = _well_formed_sensor("dq11-late", offset=0.0)
    event["timestamp"] = (_BASE_TS - timedelta(days=30)).strftime(
        "%Y-%m-%dT%H:%M:%S.%f"
    )[:-3] + "Z"
    return [event], {
        "scenario": "DQ11_late_event",
        "event_ids": [event["event_id"]],
        "expected_gate": None,
        "in_dlq": False,
        "bronze_rows": 1,
        "cleaned_rows": 1,
        "flattened_rows": 1,
        "note": (
            "Accepted by design. The platform distinguishes event time "
            "(payload timestamp) from ingestion time (_ingested_at), which "
            "is what makes buffered-then-replayed events from an "
            "EDGE_AUTONOMOUS window correct rather than anomalous. Confirm "
            "the row lands in the ADLS partition of its INGESTION date "
            "while retaining its original event timestamp."
        ),
    }


ALL_DQ_SCENARIOS = {
    "DQ1": dq1_valid_control,
    "DQ2": dq2_duplicate_event,
    "DQ3": dq3_missing_envelope_field,
    "DQ4": dq4_extra_envelope_field,
    "DQ5": dq5_wrong_envelope_type,
    "DQ6": dq6_empty_event_id,
    "DQ7": dq7_unparseable_timestamp,
    "DQ8": dq8_unknown_asset_type,
    "DQ9": dq9_missing_payload_field,
    "DQ10": dq10_wrong_payload_type,
    "DQ11": dq11_late_event,
}
