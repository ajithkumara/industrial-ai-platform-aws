"""
Shared Telemetry Schema

Defines the domain-agnostic Generic Envelope used by the producer and consumer.
Any asset type (vehicle, machine, sensor) is supported via the `payload` field.

Author: Ajith Kumara
Project: Industrial AI Platform
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TelemetryEvent(BaseModel):
    """
    Generic telemetry envelope.

    All asset types share this outer envelope.  Asset-specific data lives
    inside `payload` as an arbitrary dict so the consumer remains
    domain-agnostic — it validates structure, not content.

    Fields
    ------
    event_id : str
        UUID that uniquely identifies this event.
    device_id : str
        Identifier of the device / sensor that emitted the event.
    asset_type : str
        Category of the asset (e.g. 'vehicle', 'cnc_machine', 'wind_turbine').
    timestamp : str
        ISO-8601 UTC timestamp of when the event was recorded on the device.
    priority : str
        Routing priority: 'low' | 'normal' | 'high' | 'critical'.
    schema_version : str
        Semantic version of this envelope schema (e.g. '1.0.0').
    payload : dict[str, Any]
        Asset-specific telemetry fields — unvalidated at the envelope level.
    """

    # min_length=1 on the four identity fields closes a real defect found by
    # the DQ6 data-quality scenario (tests/integration/data_quality_scenarios.py):
    # an empty string is a perfectly valid `str` to Pydantic AND satisfies
    # Spark's `IS NOT NULL`, so an event with event_id="" previously passed
    # BOTH the consumer envelope gate and the Silver DLT expectation, reaching
    # Silver with a meaningless primary key. Worse, every such event shares
    # that key, so the dedup-by-event_id window in
    # dlt/silver/clean_and_deduplicate.py would collapse unrelated events into
    # a single row -- silent data loss. Rejecting at the consumer is the first
    # of two defences; the second is the TRIM(...) <> '' expectation in the
    # Silver notebook, which also protects any event that reaches Bronze by
    # another route.
    event_id: str = Field(..., min_length=1, description="UUID for the event")
    device_id: str = Field(..., min_length=1, description="Source device / sensor ID")
    asset_type: str = Field(..., min_length=1, description="Asset category")
    timestamp: str = Field(..., min_length=1, description="ISO-8601 UTC timestamp")
    priority: str = Field(
        default="normal",
        description="Routing priority: low | normal | high | critical",
    )
    schema_version: str = Field(
        default="1.0.0",
        description="Envelope schema version",
    )
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Asset-specific telemetry fields",
    )

    model_config = {"extra": "forbid"}
