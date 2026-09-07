"""
Unit tests for the canonical Generic Envelope (shared/telemetry_event.py).

These prove the envelope validates structure (event_id, device_id,
asset_type, timestamp, priority, schema_version, payload) without caring
about the domain-specific content of `payload` — any asset type's payload
must be accepted as long as the envelope itself is well-formed.
"""

import pytest
from pydantic import ValidationError

from shared.telemetry_event import TelemetryEvent


def _base_event(**overrides):
    event = {
        "event_id": "11111111-1111-1111-1111-111111111111",
        "device_id": "CAR-001",
        "asset_type": "vehicle",
        "timestamp": "2026-08-07T12:00:00+00:00",
        "priority": "normal",
        "schema_version": "1.0.0",
        "payload": {"speed_kmh": 42},
    }
    event.update(overrides)
    return event


def test_valid_vehicle_event_parses():
    event = TelemetryEvent(**_base_event())
    assert event.asset_type == "vehicle"
    assert event.payload == {"speed_kmh": 42}


def test_valid_event_accepts_arbitrary_asset_type_payload():
    """
    The envelope must be domain-agnostic: any asset_type + any payload
    shape is accepted, proving the platform does not hardcode a
    vehicle/industrial/wind_turbine schema at the envelope level.
    """
    event = TelemetryEvent(
        **_base_event(
            asset_type="wind_turbine",
            device_id="WT-042",
            payload={"rotor_rpm": 12.5, "wind_speed_mps": 8.1, "nested": {"a": 1}},
        )
    )
    assert event.asset_type == "wind_turbine"
    assert event.payload["nested"] == {"a": 1}


def test_missing_required_field_rejected():
    data = _base_event()
    del data["event_id"]
    with pytest.raises(ValidationError):
        TelemetryEvent(**data)


def test_missing_device_id_rejected():
    data = _base_event()
    del data["device_id"]
    with pytest.raises(ValidationError):
        TelemetryEvent(**data)


def test_missing_asset_type_rejected():
    data = _base_event()
    del data["asset_type"]
    with pytest.raises(ValidationError):
        TelemetryEvent(**data)


def test_extra_top_level_field_rejected():
    """model_config = {"extra": "forbid"} must reject unknown envelope keys."""
    data = _base_event()
    data["unexpected_field"] = "should not be allowed"
    with pytest.raises(ValidationError):
        TelemetryEvent(**data)


def test_priority_and_schema_version_have_defaults():
    data = _base_event()
    del data["priority"]
    del data["schema_version"]
    event = TelemetryEvent(**data)
    assert event.priority == "normal"
    assert event.schema_version == "1.0.0"


def test_payload_defaults_to_empty_dict():
    data = _base_event()
    del data["payload"]
    event = TelemetryEvent(**data)
    assert event.payload == {}


def test_invalid_json_raises_validation_error():
    with pytest.raises(ValidationError):
        TelemetryEvent.model_validate_json("{not valid json")
