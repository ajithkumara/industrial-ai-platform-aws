# EVENT_CONTRACT.md — Current Azure Platform

> Phase 0D deliverable. The authoritative event contract of the CURRENT
> `industrial-ai-platform` repository, derived from source, not memory.
> The AWS port MUST preserve this contract exactly. Do not invent a replacement.

## Source of truth

`shared/telemetry_event.py` — a single Pydantic v2 `BaseModel` named
`TelemetryEvent`. This is the **Generic Envelope**: one outer schema shared
by every asset type. Asset-specific data lives inside `payload` as an
arbitrary dict, so the ingestion path validates *structure*, not *content* —
the mechanical basis of the platform's domain-agnosticism.

## The envelope (exact fields)

| Field | Type | Constraints | Default | Meaning |
|---|---|---|---|---|
| `event_id` | `str` | `min_length=1`, required | — | UUID uniquely identifying the event; also the Silver dedup key |
| `device_id` | `str` | `min_length=1`, required | — | Source device / sensor ID |
| `asset_type` | `str` | `min_length=1`, required | — | Asset category; routes config-driven flattening |
| `timestamp` | `str` | `min_length=1`, required | — | ISO-8601 UTC timestamp recorded on the device |
| `priority` | `str` | optional | `"normal"` | Routing priority: low/normal/high/critical |
| `schema_version` | `str` | optional | `"1.0.0"` | Semantic version of the envelope |
| `payload` | `dict[str, Any]` | optional | `{}` (default_factory) | Asset-specific fields — unvalidated at envelope level |

## Model configuration (contractual behaviours)

- **`model_config = {"extra": "forbid"}`** — any unknown top-level field
  raises `ValidationError`. Proven by
  `tests/test_telemetry_event.py::test_extra_top_level_field_rejected`.
- **`min_length=1` on the four identity fields** — deliberate hardening. An
  empty string is a valid `str` to Pydantic AND satisfies Spark `IS NOT
  NULL`, so `event_id=""` previously passed both the consumer gate and the
  Silver expectation, reaching Silver with a meaningless key. Every such
  event shares that key, so the dedup-by-`event_id` window collapses
  unrelated events into one row — silent data loss (DQ6). This is the FIRST
  of two defences; the second is `TRIM(...) <> ''` in the Silver notebook.

## Validation entry points

- **Consumer**: `TelemetryEvent.model_validate_json(event_body)` in
  `consumer/eventhub_consumer.py::on_event`. `ValidationError` OR
  `json.JSONDecodeError` route to the DLQ, never dropped.
- **Producers/bridge**: `edge/vehicle_producer.py` and
  `edge/nats_bearing_bridge.py` build dicts in exactly this shape. The bridge
  derives deterministic `event_id`s via `uuid5` over a fixed namespace so
  NATS at-least-once redelivery maps to the same `event_id`, which Silver
  dedup then collapses.

## Contract tests that MUST be ported

From `tests/test_telemetry_event.py`: `test_valid_vehicle_event_parses`,
`test_valid_event_accepts_arbitrary_asset_type_payload` (domain-agnosticism),
`test_missing_required_field_rejected`, `test_missing_device_id_rejected`,
`test_missing_asset_type_rejected`, `test_extra_top_level_field_rejected`,
`test_priority_and_schema_version_have_defaults`,
`test_payload_defaults_to_empty_dict`,
`test_invalid_json_raises_validation_error`.

## AWS impact

**NONE.** `shared/telemetry_event.py` has zero cloud dependencies (pure
Pydantic). Copied verbatim into `industrial-ai-platform-aws/shared/`. The
envelope is cloud-invariant: Kinesis carries the same JSON bytes Event Hubs
carried; S3 stores the same JSONL ADLS stored; Bronze/Silver/Gold parse
identical structure. Classification: **SHARED LOGIC / DOMAIN-AGNOSTIC**.
