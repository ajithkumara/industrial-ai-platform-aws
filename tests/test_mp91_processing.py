"""Phase 2 processing: duplicates, out-of-order/buffered data, bad fixes, trip splitting."""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "edge"))
from mp91_gold import build, clean  # noqa: E402

NOW = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)


def r(t, lat=43.40, lon=-79.70, speed=40.0, acc=True, frame="binary", rid=None, **kw):
    d = {"record_id": rid or f"{t}-{frame}", "device_id": "1", "fix_time": f"2026-11-24T{t}+00:00", "gps_valid": True,
         "latitude": lat, "longitude": lon, "speed_kmh": speed, "acc_on": acc, "frame_type": frame}
    d.update(kw)
    return d


def test_text_and_binary_copies_of_one_fix_become_one_record_keeping_binary_fields():
    rep = {}
    out = clean([r("10:00:00", frame="text_V1", mcc="302"), r("10:00:00", frame="binary", battery_pct=80, mileage_raw=5000)], now=NOW, report=rep)
    assert len(out) == 1 and out[0]["battery_pct"] == 80 and out[0]["mileage_raw"] == 5000 and out[0]["mcc"] == "302"
    assert rep["duplicates"] == 1


def test_resent_record_after_lost_ack_is_counted_once():
    assert len(clean([r("10:00:00", rid="same"), r("10:00:00", rid="same")], now=NOW)) == 1


def test_buffered_data_arriving_late_is_placed_in_time_order():
    arrival = [r("10:00:00"), r("10:00:30"), r("09:59:30", stored_data=True), r("09:59:00", stored_data=True)]
    rep = {}
    out = clean(arrival, now=NOW, report=rep)
    assert [x["fix_time"][11:19] for x in out] == ["09:59:00", "09:59:30", "10:00:00", "10:00:30"]
    assert rep["buffered"] == 2


def test_bad_fixes_are_dropped():
    rep = {}
    out = clean([r("10:00:00"), r("10:00:01", lat=0.0, lon=0.0), r("10:00:02", speed=400.0), r("10:00:03", gps_valid=False),
                 {**r("10:00:04"), "fix_time": "2031-01-01T00:00:00+00:00"}, {**r("10:00:05"), "fix_time": "2019-12-31T00:00:00+00:00"}],
                now=NOW, report=rep)
    assert len(out) == 1 and rep["invalid"] == 5


def test_single_gps_jump_is_dropped_but_real_movement_kept():
    pts = [r("10:00:00", lat=43.400), r("10:00:10", lat=43.401), r("10:00:20", lat=44.500),   # 120 km in 10 s
           r("10:00:30", lat=43.402)]
    rep = {}
    out = clean(pts, now=NOW, report=rep)
    assert [x["latitude"] for x in out] == [43.400, 43.401, 43.402] and rep["spikes"] == 1


def test_long_silence_with_ignition_on_splits_the_trip():
    g = build([r("10:00:00"), r("10:05:00", lat=43.41), r("11:00:00", lat=43.42), r("11:05:00", lat=43.43)], device_id="1", now=NOW)
    assert len(g["trips"]) == 2
    assert g["quality"] == {"invalid": 0, "duplicates": 0, "spikes": 0, "buffered": 0}
