"""
Measured payload sizing for the edge-push-on-escalation contract.

The decision to attach a raw waveform window to HYBRID-escalated events
trades bandwidth for cloud-side information (spectral features the edge
cannot afford to compute). That trade-off must be MEASURED, not estimated:
the difference between a stats-only event and a stats+waveform event is a
direct input to H3 (cloud cost reduction) and to the escalation-rate
analysis in Chapter 7, and an approximate figure quoted in a thesis is an
easy thing for an examiner to challenge.

This module measures the exact serialised byte cost of both payload shapes
using the SAME serialisation the producer uses (see
edge/base_producer.py::EventHubProducer._to_event_data --
json.dumps(separators=(",", ":"), ensure_ascii=False)), so the numbers
correspond to what actually crosses the wire rather than to a
pretty-printed approximation.

Reported quantities:

    stats_only_bytes            one bearing_sensor event, no waveform
    stats_plus_waveform_bytes   the same event with a raw window attached
    waveform_bytes              the difference attributable to the window
    overhead_ratio              stats_plus_waveform / stats_only

These feed the Gold-side aggregates:

    total_generated_bytes       what the edge produced
    cloud_transmitted_bytes     what actually left the edge
    escalation_bytes            the portion attributable to escalations
    egress_reduction            1 - (transmitted / generated)
"""

from __future__ import annotations

import json
import math

from edge.nats_bearing_bridge import translate_sensor_record

# Matches EventHubProducer._to_event_data exactly.
_SERIALISE_KWARGS = {"separators": (",", ":"), "ensure_ascii": False}

# CWRU drive-end recordings are sampled at 12 kHz; 2048 samples is a
# standard analysis window (a power of two, so the FFT is efficient, and
# ~171 ms of signal at 12 kHz, which spans several shaft revolutions at
# typical test speeds and therefore contains multiple fault impacts).
DEFAULT_SAMPLING_RATE_HZ = 12000
DEFAULT_WINDOW_SAMPLES = 2048


def _synthetic_waveform(n: int = DEFAULT_WINDOW_SAMPLES) -> list[float]:
    """
    A deterministic waveform of realistic magnitude and precision.

    Precision matters for sizing: real accelerometer readings serialise to
    many significant figures, and rounding them to 2 decimal places would
    understate the true payload by a large factor. Values here are rounded
    to 6 decimals, which is representative of float32-derived readings.
    """
    return [
        round(0.05 * math.sin(2 * math.pi * 60 * i / DEFAULT_SAMPLING_RATE_HZ)
              + 0.01 * math.sin(2 * math.pi * 3600 * i / DEFAULT_SAMPLING_RATE_HZ), 6)
        for i in range(n)
    ]


def _base_sensor_event(with_waveform: bool, window_samples: int) -> dict:
    raw = {
        "ts": "2026-08-12T12:00:00.000Z",
        "seq": 4242,
        "sensor_id": "bearing.DE",
        "file": "inner_race_0hp.mat",
        "label": "inner_race",
        "window_idx": 17,
        "sampling_rate_hz": DEFAULT_SAMPLING_RATE_HZ,
        "features": {
            "rms": 0.2231, "peak": 0.6842, "crest": 4.2103, "kurtosis": 3.4417,
            "skew": -0.6021, "variance": 0.03118, "mean_abs": 0.1742,
        },
    }
    if with_waveform:
        raw["waveform"] = _synthetic_waveform(window_samples)
    return translate_sensor_record(raw)


def measure(window_samples: int = DEFAULT_WINDOW_SAMPLES) -> dict:
    """Measure both payload shapes and return the comparison."""
    stats_only = _base_sensor_event(False, window_samples)
    with_waveform = _base_sensor_event(True, window_samples)

    stats_only_bytes = len(json.dumps(stats_only, **_SERIALISE_KWARGS).encode("utf-8"))
    stats_plus_bytes = len(json.dumps(with_waveform, **_SERIALISE_KWARGS).encode("utf-8"))

    return {
        "window_samples": window_samples,
        "sampling_rate_hz": DEFAULT_SAMPLING_RATE_HZ,
        "stats_only_bytes": stats_only_bytes,
        "stats_plus_waveform_bytes": stats_plus_bytes,
        "waveform_bytes": stats_plus_bytes - stats_only_bytes,
        "overhead_ratio": stats_plus_bytes / stats_only_bytes,
        "bytes_per_sample": (stats_plus_bytes - stats_only_bytes) / window_samples,
        # Azure Event Hub standard tier caps a single event at 1 MiB.
        "eventhub_limit_bytes": 1024 * 1024,
        "within_eventhub_limit": stats_plus_bytes < 1024 * 1024,
    }


def projected_egress(
    total_events: int, escalation_rate: float, window_samples: int = DEFAULT_WINDOW_SAMPLES
) -> dict:
    """
    Project total transmitted bytes for a given escalation rate, against two
    reference strategies.

    static_cloud_offload  every event ships stats + waveform (the "send
                          everything to the cloud" baseline H3 compares to)
    adaptive              only escalated events ship the waveform
    edge_only             nothing is transmitted at all

    The adaptive figure is what the orchestration policy actually produces;
    the reduction against static offload is the H3 quantity.
    """
    m = measure(window_samples)
    escalated = round(total_events * escalation_rate)
    non_escalated = total_events - escalated

    static_bytes = total_events * m["stats_plus_waveform_bytes"]
    adaptive_bytes = (
        non_escalated * m["stats_only_bytes"]
        + escalated * m["stats_plus_waveform_bytes"]
    )

    return {
        **m,
        "total_events": total_events,
        "escalation_rate": escalation_rate,
        "escalated_events": escalated,
        "static_cloud_offload_bytes": static_bytes,
        "adaptive_bytes": adaptive_bytes,
        "edge_only_bytes": 0,
        "escalation_bytes": escalated * m["stats_plus_waveform_bytes"],
        "egress_reduction_vs_static": 1 - (adaptive_bytes / static_bytes),
    }


if __name__ == "__main__":
    m = measure()
    print("Measured payload sizes (as serialised by EventHubProducer):")
    print(f"  window                    : {m['window_samples']} samples "
          f"@ {m['sampling_rate_hz']} Hz")
    print(f"  stats only                : {m['stats_only_bytes']:,} bytes")
    print(f"  stats + waveform          : {m['stats_plus_waveform_bytes']:,} bytes")
    print(f"  waveform contribution     : {m['waveform_bytes']:,} bytes "
          f"({m['bytes_per_sample']:.2f} bytes/sample)")
    print(f"  overhead ratio            : {m['overhead_ratio']:.1f}x")
    print(f"  within Event Hub 1 MiB    : {m['within_eventhub_limit']}")
    print()
    print("Projected egress at varying escalation rates (10,000 events):")
    print(f"  {'rate':>6}  {'adaptive':>14}  {'static offload':>15}  {'reduction':>10}")
    for rate in (0.05, 0.10, 0.20, 0.50, 1.00):
        p = projected_egress(10_000, rate)
        print(f"  {rate:>5.0%}  {p['adaptive_bytes']:>14,}  "
              f"{p['static_cloud_offload_bytes']:>15,}  "
              f"{p['egress_reduction_vs_static']:>9.1%}")
