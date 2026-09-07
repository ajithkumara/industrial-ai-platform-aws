"""
Cloud-only synthetic event generator for the bearing_* / orchestrator_mode /
context_snapshot / cloud_validation asset types.

Purpose: prove industrial-ai-platform can consume realistic bearing
telemetry + inference + orchestration evidence and run Bronze -> Silver ->
Gold -> CloudForest WITHOUT adaptive-edge-orchestrator, NATS, or any edge
process running. Every event here is built directly in the same
TelemetryEvent-shaped dict that edge/nats_bearing_bridge.py's
translate_*_record() functions produce (reusing those functions as the
single source of truth for bearing_sensor/bearing_inference/
orchestrator_mode/context_snapshot -- so this harness can never silently
drift from what the real bridge would produce).

cloud_validation events are the one exception: they are cloud-native (see
config/asset_types/cloud_validation.yml), so this module builds them
directly with build_cloud_validation_event() rather than importing
anything edge-side.

Two different kinds of "expected value" are produced, deliberately kept
separate:

  1. EXACT, assertable expected math (Scenario B, Scenario F): every
     ground_truth_label / anomaly / cloud_anomaly value is chosen by hand
     so the resulting confusion matrix, precision/recall/F1, and
     escalation agreement rate are known in advance and can be asserted
     against gold.detection_performance / gold.escalation_efficacy
     exactly. This is what makes the eventual Gold verification "we know
     the answer" rather than "the notebook ran successfully."

  2. Structural-only expectations (Scenario C/D/E): these prove mode
     transitions, autonomy continuity, and recovery sequencing look
     right (right event counts, right trigger values, right mode
     ordering) -- but do not assert exact latency/gap numbers, since
     those are properties of when the harness happens to run, not of
     the platform's correctness.

Scenario B (HYBRID escalation, direct-synthetic) intentionally does NOT
go through the real CloudForest model -- it builds pre-computed
cloud_validation events directly, so gold.escalation_efficacy's MATH can
be verified exactly, independent of whether the real trained model
behaves any particular way. See build_cloudforest_smoke_events() for the
separate, real-model smoke path (structural-only expectations, since a
real model's output can't be known in advance).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from edge.nats_bearing_bridge import (
    translate_context_snapshot_record,
    translate_inference_record,
    translate_mode_transition_record,
    translate_sensor_record,
)

# timezone.utc rather than datetime.UTC (py3.11+) -- kept compatible with
# Python 3.10, unlike the pre-existing consumer/batch_buffer.py and
# consumer/eventhub_consumer.py, which require 3.11 (see README's
# Python-version note).
_BASE_TS = datetime(2026, 8, 12, 9, 0, 0, tzinfo=timezone.utc)

# Separate namespace from both the bridge's and score_escalations.py's --
# synthetic cloud_validation events must never collide with a real
# CloudForest-produced event_id for the same source_event_id, so a
# repeated harness run and a repeated real scoring run stay distinguishable
# if ever compared side by side.
_SYNTHETIC_CLOUD_VALIDATION_NAMESPACE = uuid.UUID(
    "3fae9c1a-0c2b-4a7e-8b1d-7e6f5a4b3c2d"
)


def _ts(offset_seconds: float) -> str:
    return (_BASE_TS + timedelta(seconds=offset_seconds)).strftime(
        "%Y-%m-%dT%H:%M:%S.%f"
    )[:-3] + "Z"


def build_cloud_validation_event(
    *,
    source_event_id: str,
    device_id: str,
    edge_anomaly: bool,
    edge_score: float,
    edge_confidence: float,
    cloud_anomaly: bool,
    cloud_score: float,
    mode: str,
    offset_seconds: float,
    edge_model_version: str = "edge-v1.0-synthetic",
    cloud_model_version: str = "cloud_forest_bearing-vSYNTHETIC",
    validation_latency_ms: float = 12.5,
) -> dict:
    """
    Build one cloud_validation TelemetryEvent directly (cloud-native asset
    type, not bridged from NATS -- see config/asset_types/cloud_validation.yml).
    Mirrors the payload shape ml/cloud_forest/score_escalations.py produces.
    """

    agrees_with_edge = cloud_anomaly == edge_anomaly
    payload = {
        "source_event_id": source_event_id,
        "edge_anomaly": edge_anomaly,
        "edge_score": edge_score,
        "edge_confidence": edge_confidence,
        "cloud_anomaly": cloud_anomaly,
        "cloud_score": cloud_score,
        "cloud_decision": "anomaly" if cloud_anomaly else "normal",
        "agrees_with_edge": agrees_with_edge,
        "edge_model_version": edge_model_version,
        "cloud_model_version": cloud_model_version,
        "validation_latency_ms": validation_latency_ms,
        "mode": mode,
    }
    return {
        "event_id": str(
            uuid.uuid5(_SYNTHETIC_CLOUD_VALIDATION_NAMESPACE, source_event_id)
        ),
        "device_id": device_id,
        "asset_type": "cloud_validation",
        "timestamp": _ts(offset_seconds),
        "priority": "high" if not agrees_with_edge else "normal",
        "schema_version": "1.0.0",
        "payload": payload,
    }


# ---------------------------------------------------------------------------
# Scenario A -- normal operation, CLOUD_OPTIMISED, nothing interesting
# ---------------------------------------------------------------------------


def scenario_a_normal_operation() -> tuple[list[dict], dict]:
    events: list[dict] = []
    for i in range(10):
        seq = i + 1
        t = i * 1.0
        sensor_raw = {
            "ts": _ts(t),
            "seq": seq,
            "sensor_id": "bearing.DE",
            "file": "normal_0hp.mat",
            "label": "normal",
            "window_idx": seq,
            "features": {
                "rms": 0.03, "peak": 0.09, "crest": 3.0, "kurtosis": 1.8,
                "skew": 0.02, "variance": 0.001, "mean_abs": 0.02,
            },
        }
        inference_raw = {
            "ts": _ts(t + 0.1),
            "seq": seq,
            "sensor_id": "bearing.DE",
            "label": "normal",
            "anomaly": False,
            "anomaly_score": 0.05,
            "infer_ms": 3.2,
            "mode": "CLOUD_OPTIMISED",
            "stats": {"total": seq, "anomalies": 0, "accuracy": 1.0, "elapsed_s": t},
        }
        events.append(translate_sensor_record(sensor_raw))
        events.append(translate_inference_record(inference_raw))

    expected = {
        "scenario": "A_normal_operation",
        "n_bearing_sensor_events": 10,
        "n_bearing_inference_events": 10,
        "detection_performance": {
            "mode": "CLOUD_OPTIMISED",
            "n_events": 10,
            "tp": 0, "fp": 0, "fn": 0, "tn": 10,
            "precision": None,  # tp+fp == 0 -> NULL by design, not 0
            "recall": None,     # tp+fn == 0 -> NULL by design, not 0
        },
    }
    return events, expected


# ---------------------------------------------------------------------------
# Scenario B -- edge uncertain, HYBRID, direct-synthetic cloud_validation
# with an EXACT, hand-computed expected escalation_efficacy row.
# ---------------------------------------------------------------------------


def scenario_b_edge_uncertain_hybrid() -> tuple[list[dict], dict]:
    # (ground_truth_label, edge_anomaly, edge_confidence, cloud_anomaly)
    # All edge_confidence values are < 0.5 -> single "low" bucket, so the
    # expected escalation_efficacy result is one clean, exact row.
    rows = [
        ("inner_race", True, 0.42, True),   # both correct, agree
        ("normal", True, 0.45, False),      # edge FP, cloud correct, disagree
        ("outer_race", True, 0.48, True),   # both correct, agree
        ("ball", False, 0.40, True),        # edge FN, cloud correct, disagree
        ("normal", False, 0.47, False),     # both correct, agree
        ("inner_race", False, 0.43, True),  # edge FN, cloud correct, disagree
    ]

    events: list[dict] = []
    inference_event_ids: list[str] = []

    for i, (label, edge_anomaly, edge_confidence, cloud_anomaly) in enumerate(rows):
        seq = 100 + i  # offset away from other scenarios' seq ranges
        t = i * 1.0
        sensor_raw = {
            "ts": _ts(t),
            "seq": seq,
            "sensor_id": "bearing.DE",
            "file": f"{label}_0hp.mat" if label != "normal" else "normal_0hp.mat",
            "label": label,
            "window_idx": seq,
            "features": {
                "rms": 0.15, "peak": 0.5, "crest": 3.8, "kurtosis": 2.3,
                "skew": -0.3, "variance": 0.015, "mean_abs": 0.1,
            },
        }
        edge_score = 0.61 if edge_anomaly else 0.35
        inference_raw = {
            "ts": _ts(t + 0.1),
            "seq": seq,
            "sensor_id": "bearing.DE",
            "label": label,
            "anomaly": edge_anomaly,
            "anomaly_score": edge_score,
            "infer_ms": 4.1,
            "mode": "HYBRID",
            "confidence": edge_confidence,  # -> edge_confidence (see YAML)
            "stats": {"total": seq, "anomalies": 1, "accuracy": 0.9, "elapsed_s": t},
        }
        inference_event = translate_inference_record(inference_raw)
        events.append(translate_sensor_record(sensor_raw))
        events.append(inference_event)
        inference_event_ids.append(inference_event["event_id"])

        cloud_score = 0.85 if cloud_anomaly else 0.15
        events.append(
            build_cloud_validation_event(
                source_event_id=inference_event["event_id"],
                device_id="bearing.DE",
                edge_anomaly=edge_anomaly,
                edge_score=edge_score,
                edge_confidence=edge_confidence,
                cloud_anomaly=cloud_anomaly,
                cloud_score=cloud_score,
                mode="HYBRID",
                offset_seconds=t + 0.2,
            )
        )

    # Hand-computed from the `rows` table above -- see module docstring.
    # agreement: rows 0,2,4 agree (3/6); edge correct: rows 0,2,4 (3/6);
    # cloud correct: all 6 (6/6).
    expected = {
        "scenario": "B_edge_uncertain_hybrid",
        "n_escalations": 6,
        "inference_event_ids": inference_event_ids,
        "escalation_efficacy": {
            "mode": "HYBRID",
            "edge_confidence_bucket": "low",
            "n_escalations": 6,
            "agreement_rate": 3 / 6,
            "edge_accuracy": 3 / 6,
            "cloud_accuracy": 6 / 6,
            "cloud_accuracy_improvement": 6 / 6 - 3 / 6,
        },
    }
    return events, expected


# ---------------------------------------------------------------------------
# Scenario C -- edge-only (cloud still reachable), structural expectations
# ---------------------------------------------------------------------------


def scenario_c_edge_only() -> tuple[list[dict], dict]:
    events: list[dict] = []

    # The breach that caused the switch.
    events.append(
        translate_context_snapshot_record(
            {
                "ts": _ts(0.0),
                "device_id": "edge-node-01",
                "rtt_ms": 40.0,
                "cpu_pct": 87.0,
                "ram_pct": 55.0,
                "cloud_reachable": True,
            },
            is_breach_sample=True,
        )
    )
    events.append(
        translate_mode_transition_record(
            {
                "ts": _ts(0.5),
                "device_id": "edge-node-01",
                "from_mode": "CLOUD_OPTIMISED",
                "to_mode": "EDGE_ONLY",
                "trigger": "cpu",
                "rtt_ms": 40.0,
                "cpu_pct": 87.0,
                "edge_confidence": 0.9,
                "breach_count": 3,
                "policy_version": "policy-v1.0-synthetic",
            }
        )
    )

    n_inference = 5
    for i in range(n_inference):
        seq = 200 + i
        t = 1.0 + i * 1.0
        inference_raw = {
            "ts": _ts(t),
            "seq": seq,
            "sensor_id": "bearing.DE",
            "label": "normal",
            "anomaly": False,
            "anomaly_score": 0.1,
            "infer_ms": 3.5,
            "mode": "EDGE_ONLY",
            "stats": {"total": seq, "anomalies": 0, "accuracy": 1.0, "elapsed_s": t},
        }
        events.append(translate_inference_record(inference_raw))

    expected = {
        "scenario": "C_edge_only",
        "n_mode_transitions": 1,
        "expected_trigger": "cpu",
        "expected_from_to": ("CLOUD_OPTIMISED", "EDGE_ONLY"),
        "n_inference_events_during_window": n_inference,
    }
    return events, expected


# ---------------------------------------------------------------------------
# Scenario D -- EDGE_AUTONOMOUS (cloud unreachable), continuity evidence
# ---------------------------------------------------------------------------


def scenario_d_autonomous() -> tuple[list[dict], dict]:
    events: list[dict] = []

    events.append(
        translate_context_snapshot_record(
            {
                "ts": _ts(0.0),
                "device_id": "edge-node-01",
                "rtt_ms": -1.0,
                "cpu_pct": 20.0,
                "ram_pct": 40.0,
                "cloud_reachable": False,
            },
            is_breach_sample=True,
        )
    )
    events.append(
        translate_mode_transition_record(
            {
                "ts": _ts(0.5),
                "device_id": "edge-node-01",
                "from_mode": "EDGE_ONLY",
                "to_mode": "EDGE_AUTONOMOUS",
                "trigger": "network",
                "rtt_ms": -1.0,
                "cpu_pct": 20.0,
                "edge_confidence": 0.9,
                "breach_count": 1,
                "policy_version": "policy-v1.0-synthetic",
            }
        )
    )

    # Evenly-spaced inference events during the outage -- proves
    # continuity (small, stable inter-event gap) for gold.edge_autonomy.
    n_events = 8
    gap_s = 2.0
    for i in range(n_events):
        seq = 300 + i
        t = 1.0 + i * gap_s
        inference_raw = {
            "ts": _ts(t),
            "seq": seq,
            # Deliberately distinct from the "bearing.DE" id shared by
            # scenarios A/B/C/F/CloudForest-smoke. gold.edge_autonomy
            # windows purely by device_id + timestamp order (gaps-and-
            # islands over consecutive EDGE_AUTONOMOUS rows); sharing an
            # id with other scenarios interleaves their events into this
            # scenario's timeline (all scenarios share one _BASE_TS) and
            # fragments the intended single 8-event outage window into
            # several 1-event windows. Must match the device_id used by
            # this scenario's own context_snapshot/mode_transition events
            # above ("edge-node-01"), since gold.mode_history and
            # gold.edge_autonomy are expected to describe the same
            # simulated device.
            "sensor_id": "edge-node-01",
            "label": "normal",
            "anomaly": i == 4,  # one real anomaly detected mid-outage
            "anomaly_score": 0.75 if i == 4 else 0.1,
            "infer_ms": 3.8,
            "mode": "EDGE_AUTONOMOUS",
            "stats": {"total": seq, "anomalies": 1 if i >= 4 else 0, "accuracy": 1.0, "elapsed_s": t},
        }
        events.append(translate_inference_record(inference_raw))

    # Heartbeat sample partway through the outage, proving continuous
    # monitoring rather than just "went dark and came back".
    events.append(
        translate_context_snapshot_record(
            {
                "ts": _ts(1.0 + 4 * gap_s),
                "device_id": "edge-node-01",
                "rtt_ms": -1.0,
                "cpu_pct": 22.0,
                "ram_pct": 41.0,
                "cloud_reachable": False,
            },
            is_breach_sample=False,
        )
    )

    expected = {
        "scenario": "D_autonomous",
        "expected_mode": "EDGE_AUTONOMOUS",
        "n_events_during_outage": n_events,
        "n_anomalies_during_outage": 1,
        "expected_gap_s": gap_s,  # largest_inter_event_gap_s should be ~= this
        "outage_duration_s": (n_events - 1) * gap_s,
    }
    return events, expected


# ---------------------------------------------------------------------------
# Scenario E -- recovery: EDGE_AUTONOMOUS -> HYBRID -> CLOUD_OPTIMISED
# ---------------------------------------------------------------------------


def scenario_e_recovery() -> tuple[list[dict], dict]:
    events: list[dict] = []

    events.append(
        translate_mode_transition_record(
            {
                "ts": _ts(0.0),
                "device_id": "edge-node-01",
                "from_mode": "EDGE_AUTONOMOUS",
                "to_mode": "HYBRID",
                "trigger": "recovery",
                "rtt_ms": 120.0,
                "cpu_pct": 18.0,
                "edge_confidence": 0.6,
                "breach_count": 0,
                "policy_version": "policy-v1.0-synthetic",
            }
        )
    )
    events.append(
        translate_context_snapshot_record(
            {
                "ts": _ts(0.2),
                "device_id": "edge-node-01",
                "rtt_ms": 120.0,
                "cpu_pct": 18.0,
                "ram_pct": 38.0,
                "cloud_reachable": True,
            },
            is_breach_sample=False,
        )
    )
    events.append(
        translate_mode_transition_record(
            {
                "ts": _ts(2.0),
                "device_id": "edge-node-01",
                "from_mode": "HYBRID",
                "to_mode": "CLOUD_OPTIMISED",
                "trigger": "recovery",
                "rtt_ms": 45.0,
                "cpu_pct": 15.0,
                "edge_confidence": 0.95,
                "breach_count": 0,
                "policy_version": "policy-v1.0-synthetic",
            }
        )
    )

    expected = {
        "scenario": "E_recovery",
        "n_mode_transitions": 2,
        "expected_sequence": [
            ("EDGE_AUTONOMOUS", "HYBRID"),
            ("HYBRID", "CLOUD_OPTIMISED"),
        ],
        "expected_trigger": "recovery",
    }
    return events, expected


# ---------------------------------------------------------------------------
# Scenario F -- the deliberate confusion matrix. EXACT expected
# precision/recall/F1, hand-verified below.
#
# TP=80, FP=5, FN=10, TN=5 (sums to 100).
#   precision = 80 / (80+5)  = 80/85  = 0.941176...
#   recall    = 80 / (80+10) = 80/90  = 0.888888...
#   f1        = 2PR/(P+R)                = 0.914285...
# ---------------------------------------------------------------------------


def scenario_f_confusion_matrix() -> tuple[list[dict], dict]:
    events: list[dict] = []
    fault_labels = ["inner_race", "outer_race", "ball"]

    def _build(idx: int, ground_truth: str, anomaly: bool) -> dict:
        seq = 1000 + idx
        t = idx * 0.5
        inference_raw = {
            "ts": _ts(t),
            "seq": seq,
            "sensor_id": "bearing.DE",
            "label": ground_truth,
            "anomaly": anomaly,
            "anomaly_score": 0.8 if anomaly else 0.2,
            "infer_ms": 3.0 + (idx % 5) * 0.5,
            "mode": "CLOUD_OPTIMISED",
            "confidence": 0.9,
            "model_version": "edge-v1.0-synthetic",
            "stats": {"total": idx + 1, "anomalies": idx, "accuracy": 0.9, "elapsed_s": t},
        }
        return translate_inference_record(inference_raw)

    idx = 0
    for _ in range(80):  # TP: real fault, correctly flagged
        events.append(_build(idx, fault_labels[idx % 3], True))
        idx += 1
    for _ in range(5):  # FP: normal, incorrectly flagged
        events.append(_build(idx, "normal", True))
        idx += 1
    for _ in range(10):  # FN: real fault, missed
        events.append(_build(idx, fault_labels[idx % 3], False))
        idx += 1
    for _ in range(5):  # TN: normal, correctly not flagged
        events.append(_build(idx, "normal", False))
        idx += 1

    assert idx == 100

    precision = 80 / 85
    recall = 80 / 90
    f1 = 2 * precision * recall / (precision + recall)

    expected = {
        "scenario": "F_confusion_matrix",
        "n_events": 100,
        "detection_performance": {
            "mode": "CLOUD_OPTIMISED",
            "model_version": "edge-v1.0-synthetic",
            "tp": 80, "fp": 5, "fn": 10, "tn": 5,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        },
    }
    return events, expected


# ---------------------------------------------------------------------------
# CloudForest real-model smoke path (structural-only expectations -- a real
# trained model's exact output can't be known in advance, unlike Scenario B).
# ---------------------------------------------------------------------------


def build_cloudforest_smoke_events() -> tuple[list[dict], dict]:
    """
    bearing_sensor + bearing_inference pairs, HYBRID mode, low edge
    confidence, WITHOUT any pre-built cloud_validation -- intended to be
    picked up and scored by the real, deployed
    ml/cloud_forest/score_escalations.py job. Only structural
    expectations are asserted (a cloud_validation row exists per
    source_event_id, with a valid correlation and score range) -- not
    exact agreement/accuracy numbers, since those depend on how the real
    trained model scores this data.
    """

    events: list[dict] = []
    inference_event_ids: list[str] = []
    labels = ["inner_race", "normal", "outer_race", "ball", "normal"]

    for i, label in enumerate(labels):
        seq = 500 + i
        t = i * 1.0
        sensor_raw = {
            "ts": _ts(t),
            "seq": seq,
            "sensor_id": "bearing.DE",
            "file": f"{label}_0hp.mat" if label != "normal" else "normal_0hp.mat",
            "label": label,
            "window_idx": seq,
            "features": {
                "rms": 0.14, "peak": 0.47, "crest": 3.7, "kurtosis": 2.2,
                "skew": -0.28, "variance": 0.014, "mean_abs": 0.095,
            },
        }
        inference_raw = {
            "ts": _ts(t + 0.1),
            "seq": seq,
            "sensor_id": "bearing.DE",
            "label": label,
            "anomaly": label != "normal",
            "anomaly_score": 0.58,
            "infer_ms": 4.0,
            "mode": "HYBRID",
            "confidence": 0.44,
            "model_version": "edge-v1.0-synthetic",
            "stats": {"total": seq, "anomalies": 1, "accuracy": 0.85, "elapsed_s": t},
        }
        inference_event = translate_inference_record(inference_raw)
        events.append(translate_sensor_record(sensor_raw))
        events.append(inference_event)
        inference_event_ids.append(inference_event["event_id"])

    expected = {
        "scenario": "cloudforest_smoke",
        "n_pending_escalations": len(labels),
        "inference_event_ids": inference_event_ids,
        "note": (
            "Structural-only: after ml/cloud_forest/score_escalations.py "
            "runs, expect exactly one silver_cloud_validation_results row "
            "per inference_event_id above, with cloud_score in [0,1] and "
            "cloud_model_version starting with 'cloud_forest_bearing-v'. "
            "Exact cloud_anomaly/agrees_with_edge values are NOT asserted "
            "here -- they depend on the real trained model."
        ),
    }
    return events, expected


ALL_SCENARIOS = {
    "A": scenario_a_normal_operation,
    "B": scenario_b_edge_uncertain_hybrid,
    "C": scenario_c_edge_only,
    "D": scenario_d_autonomous,
    "E": scenario_e_recovery,
    "F": scenario_f_confusion_matrix,
}
