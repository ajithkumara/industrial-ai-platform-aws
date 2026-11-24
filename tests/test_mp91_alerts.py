"""Alert rules: fire on transitions only, never replay history, respect settings."""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "edge"))
from mp91_alerts import evaluate, merged_settings  # noqa: E402

NOW = datetime(2026, 11, 24, 15, 0, tzinfo=timezone.utc)   # 10:00 Toronto, Tuesday


def pt(minutes_ago, speed=40.0, acc=True, lat=43.40, lon=-79.70):
    return {"fix_time": (NOW - timedelta(minutes=minutes_ago)).isoformat(), "speed_kmh": speed, "acc_on": acc, "latitude": lat, "longitude": lon}


def dev(last_min_ago=1, alarms=(), battery=100):
    return {"last_contact": (NOW - timedelta(minutes=last_min_ago)).isoformat(), "gps_valid": True, "battery_pct": battery, "alarms": list(alarms)}


def kinds(alerts):
    return [a["kind"] for a in alerts]


def test_first_run_does_not_replay_history():
    pts = [pt(300, speed=150), pt(299, speed=150)]           # speeding 5 h ago
    alerts, st = evaluate(pts, dev(), {}, {}, NOW)
    assert alerts == [] and st["watermark"] == pts[-1]["fix_time"]


def test_speeding_once_per_trip():
    st = {"watermark": pt(60)["fix_time"], "acc_on": False}
    pts = [pt(5, 50), pt(4, 130), pt(3, 140), pt(2, 0, acc=False), pt(1, 130)]   # two trips, both over
    alerts, st = evaluate(pts, dev(), {"speed_limit_kmh": 110}, st, NOW)
    assert kinds(alerts) == ["speeding", "speeding"]
    again, _ = evaluate(pts, dev(), {"speed_limit_kmh": 110}, st, NOW)              # same data again
    assert again == []


def test_speed_limit_zero_disables():
    alerts, _ = evaluate([pt(1, 200)], dev(), {"speed_limit_kmh": 0}, {"watermark": pt(60)["fix_time"]}, NOW)
    assert "speeding" not in kinds(alerts)


def test_offline_fires_once_and_back_online_after():
    alerts, st = evaluate([], dev(last_min_ago=200), {}, {"watermark": pt(300)["fix_time"]}, NOW)
    assert kinds(alerts) == ["offline"]
    alerts, st = evaluate([], dev(last_min_ago=210), {}, st, NOW)
    assert alerts == []
    alerts, st = evaluate([], dev(last_min_ago=1), {}, st, NOW)
    assert kinds(alerts) == ["back_online"]


def test_parked_tracker_heartbeat_gap_is_not_offline():
    alerts, _ = evaluate([], dev(last_min_ago=25), {}, {"watermark": pt(60)["fix_time"]}, NOW)
    assert alerts == []


def test_unplugged_and_low_battery_once_per_episode():
    st = {"watermark": pt(60)["fix_time"]}
    alerts, st = evaluate([], dev(alarms=["external_power_disconnected"], battery=10), {}, st, NOW)
    assert sorted(kinds(alerts)) == ["low_battery", "unplugged"]
    alerts, st = evaluate([], dev(alarms=["external_power_disconnected"], battery=10), {}, st, NOW)
    assert alerts == []
    alerts, st = evaluate([], dev(), {}, st, NOW)                                   # cleared: re-armed
    alerts, st = evaluate([], dev(alarms=["external_power_disconnected"]), {}, st, NOW)
    assert kinds(alerts) == ["unplugged"]


def test_after_hours_uses_local_time():
    ah = {"after_hours": {"enabled": True, "start": "07:00", "end": "19:00", "days": [0, 1, 2, 3, 4]}}
    night = NOW.replace(hour=4)            # 23:00 Toronto Monday
    st = {"watermark": (night - timedelta(hours=1)).isoformat(), "acc_on": False}
    p = {"fix_time": night.isoformat(), "speed_kmh": 10, "acc_on": True, "latitude": 43.4, "longitude": -79.7}
    alerts, _ = evaluate([p], dev(), ah, st, night)
    assert kinds(alerts) == ["after_hours"]
    st = {"watermark": pt(60)["fix_time"], "acc_on": False}
    alerts, _ = evaluate([pt(1)], dev(), ah, st, NOW)                               # 10:00 Tuesday: fine
    assert alerts == []


def test_geofence_enter_and_exit():
    g = {"geofences": [{"id": "home", "name": "Home", "lat": 43.40, "lon": -79.70, "radius_m": 200}], "speed_limit_kmh": 0}
    st = {"watermark": pt(60)["fix_time"]}
    alerts, st = evaluate([pt(5, lat=43.45), pt(4, lat=43.401), pt(3, lat=43.401), pt(2, lat=43.42)], dev(), g, st, NOW)
    assert [(a["kind"], a["title"]) for a in alerts] == [("geofence_enter", "Arrived at Home"), ("geofence_exit", "Left Home")]


def test_geofence_first_run_sets_position_without_alerting():
    g = {"geofences": [{"id": "home", "name": "Home", "lat": 43.40, "lon": -79.70, "radius_m": 200}]}
    alerts, st = evaluate([pt(1, speed=0, acc=False)], dev(), g, {}, NOW)
    assert alerts == [] and st["inside"] == ["home"]


def test_disabled_account_gets_nothing():
    alerts, _ = evaluate([pt(1, 300)], dev(last_min_ago=999), {"enabled": False}, {"watermark": pt(60)["fix_time"]}, NOW)
    assert alerts == []


def test_settings_merge_keeps_defaults():
    s = merged_settings({"after_hours": {"enabled": True}})
    assert s["after_hours"]["start"] == "07:00" and s["speed_limit_kmh"] == 110
