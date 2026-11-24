"""MP91 gold layer: route, trips and parking periods from silver records.

Pure stdlib so it runs unchanged in Lambda, in tests and in the local
dashboard builder.

Definitions (driven by the ACC/ignition flag, confirmed on 2026-11-07 drives):
  trip    = contiguous run of records with acc_on = True
  parking = gap between a trip's last ACC-on record and the next trip's first
            ACC-on record. A parking period with no following trip is
            "ongoing" (end = None).
"""
from __future__ import annotations

import math
from datetime import datetime, timezone


def _t(r):
    return datetime.fromisoformat(r["fix_time"])


def haversine_km(a, b):
    p = math.pi / 180
    dlat = (b["latitude"] - a["latitude"]) * p
    dlon = (b["longitude"] - a["longitude"]) * p
    x = math.sin(dlat / 2) ** 2 + math.cos(a["latitude"] * p) * math.cos(b["latitude"] * p) * math.sin(dlon / 2) ** 2
    return 12742 * math.asin(math.sqrt(x))


MAX_SPEED_KMH = 250        # faster than this (reported or implied) = GPS error
MAX_FUTURE_S = 600         # fix times more than 10 min ahead of the server clock are bogus
MIN_FIX_TIME = "2020-01-01"
SPIKE_MIN_KM = 1.0         # only call a jump a spike if it is also far (tiny jitter is harmless)
TRIP_GAP_MIN = 15          # ignition-on records further apart than this start a new trip


def clean(records, now=None, report=None):
    """Valid, de-duplicated, time-ordered fixes.

    - Only GPS-valid fixes with sane coordinates, timestamps and speed.
    - One record per (device, fix_time): the MP91 often sends the same fix as a text AND a binary
      frame, and resends after a lost ack. The binary frame is preferred (it carries battery and
      mileage); missing fields are filled from the other copies.
    - Sorted by the device's fix time, not arrival time, so data buffered during a coverage gap
      and uploaded later lands in the right place.
    - Single-point GPS jumps (implied speed > MAX_SPEED_KMH over > SPIKE_MIN_KM) are dropped.
    `report`, if given, is filled with counts for the quality block."""
    now = now or datetime.now(timezone.utc)
    latest_ok = (now.timestamp() + MAX_FUTURE_S)
    rep = report if report is not None else {}
    rep.update(invalid=0, duplicates=0, spikes=0, buffered=0)
    groups = {}
    for r in records:
        ok = (r.get("gps_valid") and not (abs(r["latitude"]) < 1e-6 and abs(r["longitude"]) < 1e-6)
              and r.get("speed_kmh", 0) <= MAX_SPEED_KMH and r["fix_time"] >= MIN_FIX_TIME)
        if ok:
            try:
                ok = _t(r).timestamp() <= latest_ok
            except ValueError:
                ok = False
        if not ok:
            rep["invalid"] += 1
            continue
        groups.setdefault((r["device_id"], r["fix_time"]), []).append(r)

    merged = []
    for copies in groups.values():
        copies.sort(key=lambda r: 0 if r.get("frame_type") == "binary" else 1)
        base = dict(copies[0])
        for other in copies[1:]:
            for k, v in other.items():
                if base.get(k) is None and v is not None:
                    base[k] = v
        base["stored_data"] = any(c.get("stored_data") for c in copies)
        rep["duplicates"] += len({c["record_id"] for c in copies}) - 1
        rep["buffered"] += 1 if base["stored_data"] else 0
        merged.append(base)
    merged.sort(key=lambda r: (r["device_id"], r["fix_time"]))

    out, prev = [], {}
    for r in merged:
        p = prev.get(r["device_id"])
        if p is not None:
            km = haversine_km(p, r)
            hours = max((_t(r) - _t(p)).total_seconds(), 1) / 3600
            if km > SPIKE_MIN_KM and km / hours > MAX_SPEED_KMH:
                rep["spikes"] += 1
                continue
        prev[r["device_id"]] = r
        out.append(r)
    return sorted(out, key=lambda r: r["fix_time"])


# Alarm flags decoded by h02_parser (negative logic already applied). stored_data is not an alarm.
ALARMS = ("alarm_towed", "fuel_power_cut", "alarm_battery_removed", "alarm_shake", "external_power_disconnected",
          "door_open", "alarm_fence", "alarm_sos", "alarm_overspeed", "alarm_unauthorized_ignition",
          "alarm_unauthorized_door", "vehicle_battery_low", "backup_battery_low")


def device_health(records, device_id):
    """What the device itself reports, from ALL its messages (including ones without a GPS fix):
    last contact, whether the last message had a fix, battery, odometer and active alarms.
    Values the MP91 never sent stay None, so the app can say 'not reported' instead of guessing."""
    msgs = sorted((r for r in records if r.get("device_id") == device_id), key=lambda r: r["fix_time"])
    if not msgs:
        return None
    last = msgs[-1]
    battery = next((r["battery_pct"] for r in reversed(msgs) if r.get("battery_pct") is not None), None)
    mileage = next((r["mileage_raw"] for r in reversed(msgs) if r.get("mileage_raw")), None)
    return {
        "last_contact": last["fix_time"],
        "gps_valid": bool(last.get("gps_valid")),
        "battery_pct": battery,
        "odometer_km": round(mileage / 1000, 1) if mileage else None,  # unit assumed metres (matches trip distances)
        "alarms": [a for a in ALARMS if last.get(a)],
        "messages": len(msgs),
    }


def build(records, device_id="7018532019", now=None):
    quality = {}
    pts = clean([r for r in records if r.get("device_id") == device_id], now=now, report=quality)
    trips, cur = [], None
    for r in pts:
        if r.get("acc_on"):
            # a long silence with ignition still on (lost ignition-off reports) starts a new trip
            if cur is not None and (_t(r) - _t(cur[-1])).total_seconds() > TRIP_GAP_MIN * 60:
                cur = None
            if cur is None:
                cur = [r]
                trips.append(cur)
            else:
                cur.append(r)
        else:
            cur = None

    trip_out = []
    for i, tr in enumerate(trips, 1):
        miles = [r["mileage_raw"] for r in tr if r.get("mileage_raw")]
        gps_km = sum(haversine_km(a, b) for a, b in zip(tr, tr[1:]))
        trip_out.append({
            "trip_no": i,
            "start": tr[0]["fix_time"],
            "end": tr[-1]["fix_time"],
            "duration_min": round((_t(tr[-1]) - _t(tr[0])).total_seconds() / 60, 1),
            "distance_km": round((miles[-1] - miles[0]) / 1000, 2) if len(miles) > 1 else round(gps_km, 2),
            "max_speed_kmh": max(r["speed_kmh"] for r in tr),
            "avg_moving_speed_kmh": round(
                sum(r["speed_kmh"] for r in tr if r["speed_kmh"] > 3) / max(1, sum(1 for r in tr if r["speed_kmh"] > 3)), 1),
            "start_lat": tr[0]["latitude"], "start_lon": tr[0]["longitude"],
            "end_lat": tr[-1]["latitude"], "end_lon": tr[-1]["longitude"],
            "points": [[r["latitude"], r["longitude"], r["speed_kmh"], r["fix_time"]] for r in tr],
        })

    parking = []
    for a, b in zip(trip_out, trip_out[1:] + [None]):
        start = a["end"]
        end = b["start"] if b else None
        dur = (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds() / 60 if end else None
        parking.append({
            "start": start, "end": end,
            "duration_min": round(dur, 1) if dur is not None else None,
            "lat": a["end_lat"], "lon": a["end_lon"],
        })
    # parking before the first trip of the window
    if trip_out and pts and pts[0]["fix_time"] < trip_out[0]["start"]:
        first = pts[0]
        parking.insert(0, {
            "start": first["fix_time"], "end": trip_out[0]["start"],
            "duration_min": round((datetime.fromisoformat(trip_out[0]["start"]) - _t(first)).total_seconds() / 60, 1),
            "lat": first["latitude"], "lon": first["longitude"], "note": "parked since before data window",
        })

    last = pts[-1] if pts else None
    return {
        "device": device_health(records, device_id),
        "quality": quality,
        "device_id": device_id,
        "generated_from": {"records": len(pts),
                           "first": pts[0]["fix_time"] if pts else None,
                           "last": last["fix_time"] if last else None},
        "current": None if not last else {
            "fix_time": last["fix_time"], "lat": last["latitude"], "lon": last["longitude"],
            "acc_on": last["acc_on"], "speed_kmh": last["speed_kmh"],
            "battery_pct": last.get("battery_pct"),
        },
        "totals": {
            "trips": len(trip_out),
            "distance_km": round(sum(t["distance_km"] for t in trip_out), 2),
            "driving_min": round(sum(t["duration_min"] for t in trip_out), 1),
            "max_speed_kmh": max((t["max_speed_kmh"] for t in trip_out), default=0),
        },
        "trips": trip_out,
        "parking": parking,
    }
