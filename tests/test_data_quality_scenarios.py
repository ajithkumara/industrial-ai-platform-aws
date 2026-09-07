"""
Offline verification of tests/integration/data_quality_scenarios.py.

Gate 1 (consumer envelope validation) is pure Pydantic and can therefore be
verified locally, with no Azure or Databricks involvement. These tests assert
that each scenario's declared `expected_gate` actually matches what Pydantic
does -- so a scenario claiming "GATE 1 rejects this" is proven to be rejected,
and a scenario claiming it reaches Bronze is proven to pass validation.

Gates 2 and 3 execute inside Spark/DLT and are verified against the live
platform via the queries printed by cloud_e2e_scenario.py; they cannot be
asserted here. What IS asserted here is that the scenarios are internally
consistent, so a live-run failure indicates a genuine platform defect rather
than a malformed test fixture.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from shared.telemetry_event import TelemetryEvent
from tests.integration.data_quality_scenarios import ALL_DQ_SCENARIOS

# Scenarios whose events must be REJECTED by the consumer's Pydantic
# validation (gate 1) and therefore never reach Bronze.
# DQ6 joined this set once the empty-event_id defect it found was fixed.
_GATE1_REJECTED = {"DQ3", "DQ4", "DQ5", "DQ6"}


def test_every_scenario_declares_a_complete_expectation():
    required = {
        "scenario", "event_ids", "expected_gate",
        "in_dlq", "bronze_rows", "cleaned_rows", "flattened_rows",
    }
    for key, builder in ALL_DQ_SCENARIOS.items():
        _events, expected = builder()
        missing = required - set(expected)
        assert not missing, f"{key} is missing expectation keys: {missing}"


@pytest.mark.parametrize("key", sorted(_GATE1_REJECTED))
def test_gate1_scenarios_are_actually_rejected_by_pydantic(key):
    events, expected = ALL_DQ_SCENARIOS[key]()
    assert expected["in_dlq"] is True
    assert expected["bronze_rows"] == 0
    for event in events:
        with pytest.raises(ValidationError):
            TelemetryEvent.model_validate(event)


@pytest.mark.parametrize(
    "key", sorted(set(ALL_DQ_SCENARIOS) - _GATE1_REJECTED)
)
def test_non_gate1_scenarios_actually_pass_pydantic(key):
    """
    Every scenario NOT expected to be caught at gate 1 must genuinely pass
    envelope validation -- otherwise it would be silently DLQ'd and its
    gate 2 / gate 3 expectations could never be exercised, producing a
    misleading "no rows found" result on the live platform.
    """
    events, expected = ALL_DQ_SCENARIOS[key]()
    assert expected["in_dlq"] is False
    assert expected["bronze_rows"] >= 1
    for event in events:
        TelemetryEvent.model_validate(event)  # must not raise


def test_dq6_empty_identity_fields_are_now_rejected():
    """
    Regression guard for the defect this suite found. An empty-string
    event_id must now be rejected at the consumer (min_length=1), so it can
    never reach Bronze and can never collide with other empty-id events in
    Silver's dedup window.

    Also covers the sibling identity fields, since the same reasoning
    applies to each: device_id and asset_type both participate in
    downstream grouping, and an empty asset_type would silently produce an
    unroutable event.
    """
    events, expected = ALL_DQ_SCENARIOS["DQ6"]()
    assert expected["in_dlq"] is True
    assert expected["bronze_rows"] == 0

    with pytest.raises(ValidationError):
        TelemetryEvent.model_validate(events[0])

    base = {
        "event_id": "e1", "device_id": "d1", "asset_type": "bearing_sensor",
        "timestamp": "2026-08-12T12:00:00.000Z", "payload": {},
    }
    for field in ("event_id", "device_id", "asset_type", "timestamp"):
        with pytest.raises(ValidationError):
            TelemetryEvent.model_validate({**base, field: ""})


def test_dq2_duplicate_emits_two_events_with_one_identical_id():
    events, expected = ALL_DQ_SCENARIOS["DQ2"]()
    assert len(events) == 2
    assert events[0]["event_id"] == events[1]["event_id"]
    assert expected["bronze_rows"] == 2
    assert expected["cleaned_rows"] == 1


def test_dq9_and_dq10_declare_the_columns_expected_to_be_null():
    for key, column in (("DQ9", "rms"), ("DQ10", "kurtosis")):
        _events, expected = ALL_DQ_SCENARIOS[key]()
        assert expected.get("expect_null_columns") == [column]
        assert expected["flattened_rows"] == 1, (
            "The row must still be produced -- a partial payload should "
            "degrade to a NULL column, not drop the record."
        )


def test_scenario_event_ids_are_unique_across_scenarios():
    """
    Distinct scenarios must not share event_ids, or Silver's dedup would
    merge them and make the per-scenario row counts unverifiable. DQ6 is
    excluded: its whole point is that its id is the empty string.
    """
    seen: dict[str, str] = {}
    for key, builder in ALL_DQ_SCENARIOS.items():
        if key == "DQ6":
            continue
        events, _ = builder()
        for event in events:
            eid = event.get("event_id")
            if eid is None:
                continue  # DQ3 deliberately has no event_id
            if eid in seen and seen[eid] != key:
                pytest.fail(f"event_id {eid} shared by {seen[eid]} and {key}")
            seen[eid] = key
