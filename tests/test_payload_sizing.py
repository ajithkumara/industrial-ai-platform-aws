"""
Tests for tests/integration/payload_sizing.py.

Deliberately does NOT pin exact byte counts -- those legitimately change
when the event contract gains a field, and a brittle assertion would turn a
normal schema change into a spurious failure. What is pinned are the
invariants that the orchestration argument depends on, so that if any of
them stops holding, the thesis claim built on it is invalidated loudly
rather than silently.
"""

from __future__ import annotations

from tests.integration.payload_sizing import (
    DEFAULT_WINDOW_SAMPLES,
    measure,
    projected_egress,
)


def test_waveform_dominates_the_escalated_payload():
    m = measure()
    assert m["waveform_bytes"] > 0
    # The waveform must be the overwhelming majority of an escalated event,
    # otherwise "escalation costs bandwidth" is not actually true and the
    # whole edge-push design decision would need revisiting.
    assert m["waveform_bytes"] / m["stats_plus_waveform_bytes"] > 0.9
    assert m["overhead_ratio"] > 10


def test_escalated_payload_fits_within_event_hub_limits():
    """
    A single Event Hub event is capped at 1 MiB on the standard tier. If a
    window size ever pushes past that, escalated events would be rejected
    at the transport layer -- a failure that would surface as missing
    cloud_validation rows and be very hard to diagnose from Gold alone.
    """
    m = measure()
    assert m["within_eventhub_limit"] is True
    # Even a 4x larger analysis window must still fit, so the window size
    # can be increased for a spectral-resolution experiment without
    # silently breaking ingestion.
    bigger = measure(window_samples=DEFAULT_WINDOW_SAMPLES * 4)
    assert bigger["within_eventhub_limit"] is True


def test_waveform_cost_scales_linearly_with_window_size():
    small = measure(window_samples=512)
    large = measure(window_samples=2048)
    ratio = large["waveform_bytes"] / small["waveform_bytes"]
    # 4x the samples should cost ~4x the bytes (JSON has minor per-value
    # variance from differing decimal representations, hence the tolerance).
    assert 3.5 < ratio < 4.5


def test_egress_reduction_falls_as_escalation_rate_rises():
    reductions = [
        projected_egress(1000, rate)["egress_reduction_vs_static"]
        for rate in (0.05, 0.10, 0.25, 0.50)
    ]
    assert reductions == sorted(reductions, reverse=True)
    # At 100% escalation the adaptive policy is, by construction, identical
    # to static cloud offload -- there is no saving left to claim.
    full = projected_egress(1000, 1.0)
    assert abs(full["egress_reduction_vs_static"]) < 1e-9
    assert full["adaptive_bytes"] == full["static_cloud_offload_bytes"]


def test_h3_target_is_met_at_plausible_escalation_rates():
    """
    H3 targets a >= 40% reduction in cloud operational cost versus static
    cloud-offload. This test records the escalation rate at which that
    target stops being met, so the thesis can state the condition under
    which H3 holds rather than asserting it unconditionally.
    """
    assert projected_egress(10_000, 0.20)["egress_reduction_vs_static"] > 0.40
    # Break-even: beyond roughly 60% escalation the 40% target is no longer
    # achievable on bandwidth alone.
    assert projected_egress(10_000, 0.60)["egress_reduction_vs_static"] < 0.40


def test_projection_accounting_is_internally_consistent():
    p = projected_egress(1000, 0.10)
    assert p["escalated_events"] == 100
    expected = (
        900 * p["stats_only_bytes"] + 100 * p["stats_plus_waveform_bytes"]
    )
    assert p["adaptive_bytes"] == expected
    assert p["static_cloud_offload_bytes"] == 1000 * p["stats_plus_waveform_bytes"]
