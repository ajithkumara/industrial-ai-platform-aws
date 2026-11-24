"""Edge hot path: hand-written SigV4 must match botocore's, and the publisher must only push
when the car is moving AND someone is watching."""
import datetime
import json
import os
import sys
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "edge"))
import live_push  # noqa: E402


def test_sigv4_matches_botocore(monkeypatch):
    from botocore import auth as bauth
    from botocore.awsrequest import AWSRequest
    from botocore.credentials import Credentials

    class FixedDT(datetime.datetime):
        @classmethod
        def utcnow(cls):
            return cls(2026, 11, 14, 22, 0, 0)

    monkeypatch.setattr(bauth, "datetime", types.SimpleNamespace(datetime=FixedDT, timedelta=datetime.timedelta))
    body = json.dumps({"TableName": "fleet", "Key": {"PK": {"S": "DEVICE#1"}, "SK": {"S": "WATCH"}}}, separators=(",", ":")).encode()
    host = "dynamodb.ca-central-1.amazonaws.com"
    req = AWSRequest(method="POST", url=f"https://{host}/", data=body,
                     headers={"Content-Type": "application/x-amz-json-1.0", "X-Amz-Target": "DynamoDB_20120810.GetItem"})
    bauth.SigV4Auth(Credentials("AKIDEXAMPLE", "secret/key+test", "tok123"), "dynamodb", "ca-central-1").add_auth(req)
    mine = live_push.sign_v4(host, "ca-central-1", "dynamodb", "DynamoDB_20120810.GetItem", body,
                             ("AKIDEXAMPLE", "secret/key+test", "tok123"), "20261114T220000Z")
    assert mine["Authorization"] == req.headers["Authorization"]


class FakeDb:
    def __init__(self, watch_until):
        self.watch_until, self.puts, self.gets = watch_until, [], 0

    def get(self, pk, sk):
        self.gets += 1
        return {"watch_until": {"N": str(self.watch_until)}} if self.watch_until else None

    def put(self, item):
        self.puts.append(item)


def rec(speed, t="2026-11-14T22:00:01+00:00", valid=True):
    return {"device_id": "7018532019", "latitude": 43.44, "longitude": -79.67, "speed_kmh": speed, "course_deg": 90,
            "acc_on": True, "fix_time": t, "gps_valid": valid}


FIX_EPOCH = 1_794_693_601.0   # 2026-11-14T22:00:01Z, the default fix time used by rec()


@pytest.fixture(autouse=True)
def _fresh_fixes(monkeypatch):
    # most tests reuse fixed 2026 timestamps; treat them as just received
    monkeypatch.setattr(live_push, "MAX_FIX_AGE_S", float("inf"))


def make(watch_until):
    return live_push.LivePublisher("fleet", "ca-central-1", log=lambda m: None, db=FakeDb(watch_until))


def test_pushes_when_moving_and_watched():
    p = make(2_000_000_000)
    p.offer(rec(40.0))
    p.flush_once(now=1_000.0)
    assert len(p.db.puts) == 1
    it = p.db.puts[0]
    assert it["PK"]["S"] == "DEVICE#7018532019" and it["SK"]["S"] == "LIVE" and it["speed_kmh"]["N"] == "40.0"


def test_ignores_parked_or_no_fix():
    p = make(2_000_000_000)
    p.offer(rec(0.0)); p.offer(rec(50.0, valid=False))
    p.flush_once(now=1_000.0)
    assert p.db.puts == [] and p.db.gets == 0   # parked frames never even look up the watch flag


def test_nothing_written_when_nobody_watching():
    p = make(None)
    p.offer(rec(40.0))
    p.flush_once(now=1_000.0)
    assert p.db.puts == []
    p2 = make(500)  # watch flag expired
    p2.offer(rec(40.0)); p2.flush_once(now=1_000.0)
    assert p2.db.puts == []


def test_at_most_one_write_per_second_and_watch_cached():
    p = make(2_000_000_000)
    p.offer(rec(40.0, "2026-11-14T22:00:01+00:00")); p.flush_once(now=1_000.0)
    p.offer(rec(41.0, "2026-11-14T22:00:02+00:00")); p.flush_once(now=1_000.4)   # too soon: held back
    assert len(p.db.puts) == 1
    p.flush_once(now=1_001.2)                                                    # released with the newest record
    assert len(p.db.puts) == 2 and p.db.puts[1]["speed_kmh"]["N"] == "41.0"
    assert p.db.gets == 1                                                         # watch answer reused for a few seconds


def test_buffered_or_old_fixes_are_never_published_as_live(monkeypatch):
    monkeypatch.setattr(live_push, "MAX_FIX_AGE_S", 60)
    p = make(2_000_000_000)
    p.offer({**rec(50.0), "stored_data": True}, now=FIX_EPOCH)      # replayed after a coverage gap
    p.offer(rec(50.0), now=FIX_EPOCH + 600)                          # arrived 10 min late
    p.flush_once(now=1_000.0)
    assert p.db.puts == []
    p.offer(rec(50.0), now=FIX_EPOCH + 2)                            # fresh fix
    p.flush_once(now=1_002.0)
    assert len(p.db.puts) == 1
