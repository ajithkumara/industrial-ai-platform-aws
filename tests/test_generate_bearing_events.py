"""
Offline sanity tests for tests/integration/generate_bearing_events.py.

These do NOT touch Azure or Databricks -- they validate the generator's
own internal consistency (every event is envelope-valid, and the
hand-computed "expected" math in Scenario B / Scenario F actually matches
what the generated events themselves encode). This exists specifically to
catch a drift bug in the harness -- e.g. someone edits scenario_b's rows
table without updating the expected agreement_rate -- BEFORE it produces
a confusing false failure (or false pass) against real Gold tables later.
"""

from __future__ import annotations

from shared.telemetry_event import TelemetryEvent
from tests.integration.generate_bearing_events import (
    ALL_SCENARIOS,
    build_cloudforest_smoke_events,
    scenario_b_edge_uncertain_hybrid,
    scenario_f_confusion_matrix,
)


def test_every_scenario_produces_only_envelope_valid_events():
    for letter, builder in ALL_SCENARIOS.items():
        events, _ = builder()
        assert len(events) > 0, f"scenario {letter} produced no events"
        for event in events:
            TelemetryEvent.model_validate(event)  # raises on invalid envelope


def test_cloudforest_smoke_events_are_envelope_valid_and_have_no_cloud_validation():
    events, expected = build_cloudforest_smoke_events()
    for event in events:
        TelemetryEvent.model_validate(event)
    asset_types = {e["asset_type"] for e in events}
    assert "cloud_validation" not in asset_types
    assert asset_types == {"bearing_sensor", "bearing_inference"}
    assert len(expected["inference_event_ids"]) == expected["n_pending_escalations"]


def test_scenario_b_agreement_rate_matches_generated_events():
    events, expected = scenario_b_edge_uncertain_hybrid()

    cloud_validation_events = [e for e in events if e["asset_type"] == "cloud_validation"]
    inference_events = {
        e["event_id"]: e for e in events if e["asset_type"] == "bearing_inference"
    }

    assert len(cloud_validation_events) == expected["n_escalations"]

    agreements = [cv["payload"]["agrees_with_edge"] for cv in cloud_validation_events]
    actual_agreement_rate = sum(agreements) / len(agreements)
    assert actual_agreement_rate == expected["escalation_efficacy"]["agreement_rate"]

    edge_correct = []
    cloud_correct = []
    for cv in cloud_validation_events:
        source = inference_events[cv["payload"]["source_event_id"]]
        ground_truth = source["payload"]["label"]
        is_actual_anomaly = ground_truth != "normal"
        edge_correct.append(cv["payload"]["edge_anomaly"] == is_actual_anomaly)
        cloud_correct.append(cv["payload"]["cloud_anomaly"] == is_actual_anomaly)

    actual_edge_accuracy = sum(edge_correct) / len(edge_correct)
    actual_cloud_accuracy = sum(cloud_correct) / len(cloud_correct)

    assert actual_edge_accuracy == expected["escalation_efficacy"]["edge_accuracy"]
    assert actual_cloud_accuracy == expected["escalation_efficacy"]["cloud_accuracy"]

    # All six rows were deliberately built with edge_confidence < 0.5 --
    # confirm they'd actually land in the "low" bucket as
    # dlt/gold/escalation_efficacy.py buckets them.
    for cv in cloud_validation_events:
        assert cv["payload"]["edge_confidence"] < 0.5


def test_scenario_b_disagreements_are_marked_high_priority():
    # build_cloud_validation_event() routes disagreements to "high"
    # priority so they're easy to find downstream -- confirm that
    # actually happened for the 3 deliberately-disagreeing rows.
    events, _ = scenario_b_edge_uncertain_hybrid()
    cloud_validation_events = [e for e in events if e["asset_type"] == "cloud_validation"]

    n_disagreements = sum(
        1 for cv in cloud_validation_events if not cv["payload"]["agrees_with_edge"]
    )
    n_high_priority = sum(1 for cv in cloud_validation_events if cv["priority"] == "high")

    assert n_disagreements == 3
    assert n_high_priority == n_disagreements


def test_scenario_f_confusion_matrix_sums_to_100_and_matches_expected_metrics():
    events, expected = scenario_f_confusion_matrix()
    inference_events = [e for e in events if e["asset_type"] == "bearing_inference"]
    assert len(inference_events) == 100

    tp = fp = fn = tn = 0
    for e in inference_events:
        ground_truth = e["payload"]["label"]
        predicted = e["payload"]["anomaly"]
        is_actual_anomaly = ground_truth != "normal"
        if predicted and is_actual_anomaly:
            tp += 1
        elif predicted and not is_actual_anomaly:
            fp += 1
        elif not predicted and is_actual_anomaly:
            fn += 1
        else:
            tn += 1

    dp = expected["detection_performance"]
    assert (tp, fp, fn, tn) == (dp["tp"], dp["fp"], dp["fn"], dp["tn"])
    assert tp + fp + fn + tn == 100

    precision = tp / (tp + fp)
    recall = tp / (tp + fn)
    f1 = 2 * precision * recall / (precision + recall)

    assert precision == dp["precision"]
    assert recall == dp["recall"]
    assert abs(f1 - dp["f1"]) < 1e-12


def test_scenario_f_events_all_share_mode_and_model_version_for_grouping():
    # gold.detection_performance groups by (mode, model_version) -- if
    # these vary within the scenario, the single expected row wouldn't
    # correspond to a single Gold row.
    events, expected = scenario_f_confusion_matrix()
    inference_events = [e for e in events if e["asset_type"] == "bearing_inference"]
    modes = {e["payload"]["mode"] for e in inference_events}
    model_versions = {e["payload"]["model_version"] for e in inference_events}
    assert modes == {expected["detection_performance"]["mode"]}
    assert model_versions == {expected["detection_performance"]["model_version"]}


def test_scenario_ids_are_deterministic_across_repeated_generation():
    # Re-running the harness (e.g. after a failed send) must produce the
    # same event_ids so Silver's dedup-by-event_id collapses any
    # accidental resend instead of double-counting it -- same invariant
    # the bridge itself guarantees.
    events_a, _ = scenario_f_confusion_matrix()
    events_b, _ = scenario_f_confusion_matrix()
    ids_a = [e["event_id"] for e in events_a]
    ids_b = [e["event_id"] for e in events_b]
    assert ids_a == ids_b
    assert len(set(ids_a)) == len(ids_a)  # also no internal collisions
