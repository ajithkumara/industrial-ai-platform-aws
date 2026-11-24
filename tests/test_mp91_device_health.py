"""Device health block in gold: last contact, GPS validity, battery, odometer, alarms."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "edge"))
from mp91_gold import build, device_health  # noqa: E402


def rec(t, valid=True, **kw):
    base = {"record_id": t, "device_id": "1", "fix_time": t, "gps_valid": valid, "latitude": 43.4, "longitude": -79.7,
            "speed_kmh": 0.0, "acc_on": False}
    base.update(kw)
    return base


def test_no_messages_means_no_device_block():
    assert device_health([], "1") is None
    assert build([], device_id="1")["device"] is None


def test_last_contact_counts_messages_without_gps():
    rs = [rec("2026-11-16T10:00:00+00:00"), rec("2026-11-16T10:20:00+00:00", valid=False)]
    d = device_health(rs, "1")
    assert d["last_contact"] == "2026-11-16T10:20:00+00:00" and d["gps_valid"] is False
    assert build(rs, device_id="1")["current"]["fix_time"] == "2026-11-16T10:00:00+00:00"  # position only from valid fixes


def test_battery_and_odometer_are_latest_reported_values_and_none_when_never_sent():
    rs = [rec("2026-11-16T10:00:00+00:00", battery_pct=80, mileage_raw=12_345_600), rec("2026-11-16T10:01:00+00:00")]
    d = device_health(rs, "1")
    assert d["battery_pct"] == 80 and d["odometer_km"] == 12345.6
    d2 = device_health([rec("2026-11-16T10:00:00+00:00")], "1")
    assert d2["battery_pct"] is None and d2["odometer_km"] is None


def test_alarms_come_from_the_last_message_only_and_exclude_stored_data():
    rs = [rec("2026-11-16T10:00:00+00:00", alarm_shake=True),
          rec("2026-11-16T10:05:00+00:00", external_power_disconnected=True, stored_data=True)]
    assert device_health(rs, "1")["alarms"] == ["external_power_disconnected"]


def test_other_devices_are_ignored():
    assert device_health([rec("2026-11-16T10:00:00+00:00", device_id="2")], "1") is None
