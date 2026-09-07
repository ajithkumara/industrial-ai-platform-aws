"""
Amazon Kinesis Producer

AWS-native translation of the Azure reference `edge/base_producer.py`
(EventHubProducerClient). Sends telemetry events to a Kinesis Data Stream.

Partition key = device_id: this distributes load across shards while keeping
all events from a single device on the same shard, preserving per-device
ordering (the AWS analogue of Event Hubs partition-key routing).

No static credentials: the boto3 client uses the ambient IAM role. The
producer calls validate_settings() on construction, exactly like the Azure
reference, so a misconfigured environment fails fast at the entry point
rather than silently.
"""

from __future__ import annotations

import json
import logging

import boto3

from config.settings import settings, validate_settings


class KinesisProducer:
    """Sends telemetry events to a Kinesis Data Stream."""

    def __init__(self, kinesis_client=None) -> None:
        validate_settings()
        self._logger = logging.getLogger(__name__)
        self._stream_name = settings.kinesis.stream_name
        # Injectable for tests (moto). Production builds from the ambient role.
        self._kinesis = kinesis_client or boto3.client(
            "kinesis", region_name=settings.kinesis.region
        )
        self._logger.info("Connected to Kinesis stream '%s'.", self._stream_name)

    @staticmethod
    def _partition_key(event: dict) -> str:
        # device_id keeps per-device ordering; fall back to event_id.
        return str(event.get("device_id") or event.get("event_id") or "unknown")

    def send_events(self, events: list[dict]) -> None:
        """Send a batch of telemetry events via a single PutRecords call."""
        if not events:
            self._logger.warning("No telemetry events to send.")
            return

        records = [
            {
                "Data": json.dumps(e, separators=(",", ":"), ensure_ascii=False).encode("utf-8"),
                "PartitionKey": self._partition_key(e),
            }
            for e in events
        ]

        resp = self._kinesis.put_records(StreamName=self._stream_name, Records=records)

        failed = resp.get("FailedRecordCount", 0)
        if failed:
            # PutRecords is partial-failure capable: some records can fail
            # while others succeed. Surface it so the caller can retry the
            # failed subset rather than assuming all-or-nothing.
            self._logger.error(
                "%d/%d records failed to send to Kinesis stream '%s'.",
                failed, len(records), self._stream_name,
            )
            raise RuntimeError(f"{failed} Kinesis record(s) failed to send")

        self._logger.info("Sent %d event(s) to Kinesis stream '%s'.",
                          len(events), self._stream_name)

    def close(self) -> None:
        # boto3 clients need no explicit close; provided for interface parity
        # with the Azure EventHubProducer.
        self._logger.info("Kinesis producer closed.")
