"""
Unit tests for consumer/batch_buffer.py.

Verifies the batching semantics described in the architecture:
 - RAW_BATCH_SIZE controls how many validated events accumulate before a
   JSONL file is written (flush to ADLS via the storage client).
 - Memory stays bounded (buffer clears after a successful flush).
 - A failed ADLS write (storage_client.upload_batch raising) must NOT
   silently discard the buffered events, so they can be retried.

P0-01 regression tests
-----------------------
After the checkpoint-ordering fix, BatchBuffer.flush() is the ONLY place
that advances the Event Hub checkpoint.  The tests below verify:
 - checkpoint_fn is NOT called when an event is merely buffered (add returns
   without triggering a flush).
 - checkpoint_fn IS called exactly once per partition after a successful
   flush, using the last offset seen in that partition's events.
 - checkpoint_fn is NOT called when upload_batch() raises (write failed).
"""

import pytest

from consumer.batch_buffer import BatchBuffer


class FakeStorageClient:
    """Test double for consumer.storage_client.StorageClient."""

    def __init__(self, fail_on_call: int | None = None):
        self.calls: list[list[dict]] = []
        self.fail_on_call = fail_on_call

    def upload_batch(self, events):
        call_number = len(self.calls) + 1
        if self.fail_on_call is not None and call_number == self.fail_on_call:
            raise RuntimeError("Simulated ADLS write failure")
        # Record a shallow copy since BatchBuffer clears its internal list
        # immediately after this call returns.
        self.calls.append(list(events))
        return f"fake/path/batch_{call_number}.jsonl"


@pytest.fixture(autouse=True)
def _small_batch_size(monkeypatch):
    """Force a small, deterministic batch size for these tests."""
    monkeypatch.setenv("RAW_BATCH_SIZE", "3")
    yield


def _reload_batch_buffer_module():
    # BatchBuffer reads settings.storage.raw_batch_size at construction time
    # via the module-level `settings` singleton, which is built once at
    # import time of config.settings. Re-import config.settings fresh so the
    # monkeypatched RAW_BATCH_SIZE env var takes effect for this test.
    import importlib

    import config.settings as settings_module

    importlib.reload(settings_module)
    return settings_module


def _make_buffer(storage, batch_size=3, checkpoint_fn=None):
    """Helper: construct a BatchBuffer with test-controlled internals."""
    buf = BatchBuffer.__new__(BatchBuffer)
    buf._logger = __import__("logging").getLogger("test")
    buf._storage_client = storage
    buf._checkpoint_fn = checkpoint_fn
    buf._buffer = []
    buf._batch_size = batch_size
    return buf


# ---------------------------------------------------------------------------
# Basic batching semantics
# ---------------------------------------------------------------------------

def test_buffer_flushes_once_batch_size_reached():
    settings_module = _reload_batch_buffer_module()

    storage = FakeStorageClient()
    buffer = _make_buffer(storage, batch_size=settings_module.settings.storage.raw_batch_size)

    buffer.add({"event_id": "1"}, "0", "100", 1)
    buffer.add({"event_id": "2"}, "0", "101", 2)
    assert buffer.pending_events() == 2
    assert len(storage.calls) == 0  # not flushed yet

    buffer.add({"event_id": "3"}, "0", "102", 3)  # hits batch_size=3 -> flush()

    assert len(storage.calls) == 1
    assert len(storage.calls[0]) == 3
    assert buffer.pending_events() == 0  # buffer cleared after successful flush


def test_failed_flush_does_not_silently_drop_events():
    """
    If the ADLS write fails, the events must remain in the buffer (not be
    lost) so the caller can retry later without data loss.
    """
    storage = FakeStorageClient(fail_on_call=1)
    buffer = _make_buffer(storage, batch_size=2)

    buffer.add({"event_id": "1"}, "0", "100", 1)

    with pytest.raises(RuntimeError):
        buffer.add({"event_id": "2"}, "0", "101", 2)  # reaches batch_size -> flush() raises

    # Buffer must still hold both events — nothing was cleared/lost.
    assert buffer.pending_events() == 2


def test_pending_events_reports_buffer_depth():
    storage = FakeStorageClient()
    buffer = _make_buffer(storage, batch_size=10)

    assert buffer.pending_events() == 0
    buffer.add({"event_id": "1"}, "0", "100", 1)
    assert buffer.pending_events() == 1


# ---------------------------------------------------------------------------
# P0-01 regression: checkpoint only fires after durable write
# ---------------------------------------------------------------------------

def test_checkpoint_not_called_on_partial_buffer():
    """
    checkpoint_fn must NOT be called when an event is merely buffered.
    Checkpointing before the batch is written to ADLS is the exact bug
    that P0-01 fixes.
    """
    checkpoints: list[tuple] = []
    storage = FakeStorageClient()
    buffer = _make_buffer(storage, batch_size=3,
                          checkpoint_fn=lambda pid, off, seq: checkpoints.append((pid, off, seq)))

    # Add two events — batch_size=3, so no flush yet.
    buffer.add({"event_id": "1"}, "0", "100", 1)
    buffer.add({"event_id": "2"}, "0", "101", 2)

    # No flush, no checkpoint.
    assert len(storage.calls) == 0
    assert checkpoints == [], (
        "checkpoint_fn was called before the batch was written to ADLS — "
        "this is the P0-01 bug."
    )


def test_checkpoint_called_after_flush_with_last_offset_per_partition():
    """
    After a successful flush, checkpoint_fn must be called exactly once per
    partition, using the LAST offset seen in that partition's events within
    the flushed batch.
    """
    checkpoints: list[tuple] = []
    storage = FakeStorageClient()
    buffer = _make_buffer(storage, batch_size=4,
                          checkpoint_fn=lambda pid, off, seq: checkpoints.append((pid, off, seq)))

    # Two partitions interleaved.
    buffer.add({"event_id": "1"}, "0", "100", 10)
    buffer.add({"event_id": "2"}, "1", "200", 20)
    buffer.add({"event_id": "3"}, "0", "101", 11)  # later offset for partition 0
    buffer.add({"event_id": "4"}, "1", "201", 21)  # hits batch_size=4 -> flush

    assert len(storage.calls) == 1
    assert len(checkpoints) == 2  # one per partition

    cp_map = {pid: (off, seq) for (pid, off, seq) in checkpoints}
    # Partition 0: last offset is "101" / seq 11
    assert cp_map["0"] == ("101", 11), f"Wrong checkpoint for partition 0: {cp_map['0']}"
    # Partition 1: last offset is "201" / seq 21
    assert cp_map["1"] == ("201", 21), f"Wrong checkpoint for partition 1: {cp_map['1']}"


def test_checkpoint_not_called_when_write_fails():
    """
    If upload_batch() raises, checkpoint_fn must NOT be called.
    Advancing the checkpoint on a failed write would lose the events.
    """
    checkpoints: list[tuple] = []
    storage = FakeStorageClient(fail_on_call=1)
    buffer = _make_buffer(storage, batch_size=2,
                          checkpoint_fn=lambda pid, off, seq: checkpoints.append((pid, off, seq)))

    buffer.add({"event_id": "1"}, "0", "100", 1)

    with pytest.raises(RuntimeError):
        buffer.add({"event_id": "2"}, "0", "101", 2)  # triggers failing flush

    assert checkpoints == [], (
        "checkpoint_fn was called despite the ADLS write failing — "
        "this would advance the checkpoint past unwritten data."
    )
    # Events must still be in the buffer for retry.
    assert buffer.pending_events() == 2


def test_explicit_flush_checkpoints_remaining_events():
    """
    An explicit flush() (e.g. on graceful shutdown) must also checkpoint
    the remaining buffered events after writing them.
    """
    checkpoints: list[tuple] = []
    storage = FakeStorageClient()
    buffer = _make_buffer(storage, batch_size=10,
                          checkpoint_fn=lambda pid, off, seq: checkpoints.append((pid, off, seq)))

    # Add 2 events (below batch_size=10 — no auto-flush).
    buffer.add({"event_id": "1"}, "0", "100", 1)
    buffer.add({"event_id": "2"}, "0", "101", 2)

    assert len(storage.calls) == 0
    assert checkpoints == []

    # Graceful shutdown: explicit flush.
    buffer.flush()

    assert len(storage.calls) == 1
    assert len(checkpoints) == 1
    assert checkpoints[0] == ("0", "101", 2)  # last offset in partition 0
    assert buffer.pending_events() == 0
