"""
DynamoDB checkpoint manager (AWS production).

Production replacement for the local-file FileCheckpointManager
(consumer/checkpoint.py). Presents the SAME interface, so the consumer's
injected _do_checkpoint callback and startup-resume logic are identical
regardless of which store is active:

    get_checkpoint(partition_id)      -> {"offset", "sequence_number"} | None
    get_starting_position(partition_id) -> str
    update_checkpoint(partition_id, offset, sequence_number) -> None
    .checkpoints                      -> in-memory mirror {partition_id: {...}}

Rationale (why DynamoDB, not the local file, in production):
  - The local JSON file is per-process and per-host; it does not survive a
    task replacement and cannot be shared across a scaled-out consumer fleet.
  - DynamoDB is the KCL-native lease/checkpoint store on AWS: durable,
    shared, and consistent, so a restarted or rebalanced consumer resumes
    from the last durably-committed sequence number per shard.
  - Partition/shard is the item key; the checkpoint is committed AFTER the
    durable S3 write (the P0-01 invariant is enforced by BatchBuffer, not by
    this store).

Failure modes: a DynamoDB write failure is surfaced (logged) but is NOT fatal
to the batch that already landed in S3 — the events may be re-read and
re-written on restart, and Silver dedup-by-event_id makes that idempotent
(same at-least-once contract as the Azure reference).

No static credentials: the boto3 resource uses the ambient IAM role.
"""

from __future__ import annotations

import boto3

from shared.logger import setup_logger

logger = setup_logger("dynamo_checkpoint")


class DynamoCheckpointManager:
    """DynamoDB-backed checkpoint store (interface-compatible with FileCheckpointManager)."""

    def __init__(self, table_name: str, region: str | None = None, dynamodb_resource=None):
        self.table_name = table_name
        # Injectable for tests (moto). Production builds from the ambient role.
        self._dynamodb = dynamodb_resource or boto3.resource("dynamodb", region_name=region)
        self._table = self._dynamodb.Table(table_name)
        self.checkpoints = self._load_checkpoints()

    def _load_checkpoints(self) -> dict:
        """Load all committed checkpoints into an in-memory mirror on startup."""
        try:
            resp = self._table.scan()
            items = resp.get("Items", [])
            checkpoints = {
                item["partition_id"]: {
                    "offset": item.get("offset"),
                    "sequence_number": item.get("sequence_number"),
                }
                for item in items
            }
            logger.info("Loaded %d partition checkpoint(s) from DynamoDB table '%s'.",
                        len(checkpoints), self.table_name)
            return checkpoints
        except Exception as e:  # noqa: BLE001
            logger.error("Error loading checkpoints from DynamoDB: %s", e)
            return {}

    def get_checkpoint(self, partition_id: str) -> dict | None:
        return self.checkpoints.get(partition_id)

    def get_starting_position(self, partition_id: str) -> str:
        checkpoint = self.get_checkpoint(partition_id)
        if checkpoint and checkpoint.get("offset"):
            return checkpoint["offset"]
        return "-1"  # start from the beginning if no checkpoint exists

    def update_checkpoint(self, partition_id: str, offset: str, sequence_number) -> None:
        """Persist the checkpoint for a shard, then update the in-memory mirror."""
        self.checkpoints[partition_id] = {"offset": offset, "sequence_number": sequence_number}
        try:
            self._table.put_item(
                Item={
                    "partition_id": partition_id,
                    "offset": offset,
                    "sequence_number": sequence_number,
                }
            )
            logger.info("Updated DynamoDB checkpoint for shard %s: offset=%s seq=%s",
                        partition_id, offset, sequence_number)
        except Exception as e:  # noqa: BLE001
            # Non-fatal: data is already durable in S3. Worst case is re-read
            # on restart (Silver dedup handles it).
            logger.error("Error updating DynamoDB checkpoint for shard %s: %s",
                         partition_id, e)
