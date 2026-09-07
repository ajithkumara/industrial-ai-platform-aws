"""
Batch Buffer

Collects telemetry events and writes them to S3 in batches.

P0-01 FIX — checkpoint ordering
================================
The previous implementation advanced the Kinesis checkpoint inside
on_event(), immediately after batch_buffer.add() returned, regardless of
whether a flush had actually occurred.  This meant that for events 1-(N-1)
of each batch the checkpoint was advanced while those events were still
only in memory.  A process crash between the add() call and the next
flush() permanently lost those events (Kinesis would not re-deliver
them because the checkpoint was already past them).

The correct at-least-once pattern is:
    1. Receive event from Kinesis.
    2. Buffer it (in memory only — no checkpoint yet).
    3. When the buffer is full (or an explicit flush is requested):
       a. Write the batch to S3.
       b. Wait for the write to be confirmed (upload_batch returns without
          raising).
       c. Checkpoint the last offset **per partition** seen in the flushed
          batch.
    4. Only then is it safe to advance past those events.

On a crash between steps 2 and 3c the consumer re-reads the buffered
events from their last checkpointed offset.  Silver-layer deduplication
by event_id makes that replay idempotent (no double-counting).

API change
----------
BatchBuffer.__init__ now accepts an optional `checkpoint_fn` callback::

    checkpoint_fn(partition_id: str, offset: str, sequence_number: int)

It is called once per partition after each successful flush.
BatchBuffer.add() now requires three extra positional arguments::

    add(event_data, partition_id, offset, sequence_number)

These are stored alongside the event dict and used to build the per-
partition checkpoint map on flush.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Callable, TYPE_CHECKING

from config.settings import settings

if TYPE_CHECKING:
    # Type-only import: the concrete S3-backed StorageClient lives in
    # consumer/storage_client.py (Milestone 2). `from __future__ import
    # annotations` makes the annotation below a string, so the domain-level
    # buffer carries NO runtime coupling to any cloud SDK.
    from .storage_client import StorageClient


class BatchBuffer:
    """
    Buffers telemetry events before writing to S3.

    Checkpoints the last Kinesis offset per partition only after a batch
    has been durably written to storage (see module docstring for rationale).
    """

    def __init__(
        self,
        storage_client: StorageClient,
        checkpoint_fn: Callable[[str, str, int], None] | None = None,
    ):
        self._logger = logging.getLogger(__name__)
        self._storage_client = storage_client
        # checkpoint_fn(partition_id, offset, sequence_number)
        self._checkpoint_fn = checkpoint_fn
        self._batch_size = settings.storage.raw_batch_size

        # Each entry: (event_dict, partition_id, offset, sequence_number)
        self._buffer: list[tuple[dict[str, Any], str, str, int]] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add(
        self,
        event: dict[str, Any],
        partition_id: str,
        offset: str,
        sequence_number: int,
    ) -> None:
        """
        Add an event to the buffer.

        Triggers a flush (write + checkpoint) when the buffer reaches
        RAW_BATCH_SIZE.  Does NOT checkpoint on a plain buffer-append —
        that is the core of the P0-01 fix.
        """
        self._buffer.append((event, partition_id, offset, sequence_number))

        self._logger.info(
            "Buffered %d/%d events",
            len(self._buffer),
            self._batch_size,
        )

        if len(self._buffer) >= self._batch_size:
            self.flush()

    def flush(self) -> None:
        """
        Write buffered events to S3, then checkpoint.

        Checkpoint is issued **after** upload_batch() returns without
        raising — i.e. after durable write is confirmed.  If upload_batch()
        raises, the checkpoint is NOT advanced and the buffer is NOT cleared,
        so the same events will be retried on the next flush() call.
        """
        if not self._buffer:
            return

        data_dicts = [item[0] for item in self._buffer]

        self._logger.info("Writing %d events to S3...", len(data_dicts))

        # --- durable write first -------------------------------------------
        # If this raises, we propagate the exception.  The caller (on_event)
        # must NOT advance the checkpoint in that case.
        self._storage_client.upload_batch(data_dicts)
        # -------------------------------------------------------------------

        # Write confirmed: now it is safe to advance the checkpoint.
        if self._checkpoint_fn is not None:
            # Build last-(offset, seq) per partition from the flushed batch.
            last_per_partition: dict[str, tuple[str, int]] = {}
            for (_, partition_id, offset, sequence_number) in self._buffer:
                last_per_partition[partition_id] = (offset, sequence_number)

            for partition_id, (offset, seq) in last_per_partition.items():
                try:
                    self._checkpoint_fn(partition_id, offset, seq)
                    self._logger.info(
                        "Checkpointed partition %s at offset %s (seq %d)",
                        partition_id, offset, seq,
                    )
                except Exception as cp_err:  # noqa: BLE001
                    # A checkpoint failure is not fatal to the write — the
                    # data is already in S3.  Log and continue; the worst
                    # case is that the events are re-read and re-written on
                    # restart (Silver deduplication handles that).
                    self._logger.error(
                        "Checkpoint failed for partition %s: %s. "
                        "Data is in S3; events may be re-read on restart.",
                        partition_id, cp_err,
                    )

        self._buffer.clear()
        self._logger.info("Batch written and checkpointed successfully.")

    def pending_events(self) -> int:
        """Returns number of events currently buffered (not yet flushed)."""
        return len(self._buffer)
