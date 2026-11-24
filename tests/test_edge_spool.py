"""Edge listener durability: fsync before ack, crash leftovers recovered, failed uploads retried."""
import importlib
import json
import os
import sys
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEXT = b"*HQ,7018532019,V1,045151,A,4326.6589,N,07940.5293,W,000.05,000,071126,FFFFFBFF,302,00,55015,140168745#"


@pytest.fixture
def lst(tmp_path, monkeypatch):
    monkeypatch.setenv("SPOOL_DIR", str(tmp_path))
    monkeypatch.setenv("S3_BUCKET", "lake-test")
    monkeypatch.delenv("FLEET_TABLE", raising=False)
    sys.path.insert(0, os.path.join(ROOT, "edge"))
    import tcp_listener_adaptive as m
    m = importlib.reload(m)
    m.current.update(path=None, fh=None, opened=0.0)
    yield m
    sys.path.remove(os.path.join(ROOT, "edge"))


def test_write_is_fsynced_before_ack(lst, monkeypatch):
    order = []
    real_fsync = os.fsync
    monkeypatch.setattr(lst.os, "fsync", lambda fd: (order.append("fsync"), real_fsync(fd)))
    sent = []

    class Conn:
        chunks = [TEXT, b""]
        def settimeout(self, t): pass
        def recv(self, n): return self.chunks.pop(0)
        def sendall(self, b): order.append("ack"); sent.append(b)
        def close(self): pass

    lst.handle(Conn(), ("1.2.3.4", 5))
    assert order == ["fsync", "ack"]
    assert sent == [b"*HQ,7018532019,R12,045151#"]


def test_crash_leftovers_are_recovered_and_empty_ones_dropped(lst, tmp_path):
    lst.write_event({"raw_hex": TEXT.hex()})
    lst.current["fh"].close()                 # simulate a crash: file never renamed
    lst.current.update(path=None, fh=None)
    (tmp_path / "mp91_20261123T000000Z_empty.jsonl.part").write_text("")
    assert lst.recover_orphans() == 1
    names = os.listdir(tmp_path)
    assert len(names) == 1 and names[0].endswith(".jsonl")
    assert json.loads((tmp_path / names[0]).read_text())["raw_hex"] == TEXT.hex()


def test_failed_upload_keeps_the_file_for_retry(lst, tmp_path, monkeypatch):
    lst.write_event({"raw_hex": "00"})
    calls = []
    def run(cmd, **kw):
        calls.append(cmd)
        return types.SimpleNamespace(returncode=1 if len(calls) == 1 else 0, stderr="network down")
    monkeypatch.setattr(lst.subprocess, "run", run)
    lst.upload_spool()
    assert len(os.listdir(tmp_path)) == 1        # failed: still on disk
    lst.upload_spool()
    assert os.listdir(tmp_path) == []            # retried and removed
    key = calls[-1][4]
    assert key.startswith("s3://lake-test/raw/mp91/year=") and key.endswith(".jsonl")
