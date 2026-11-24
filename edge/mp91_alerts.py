"""FleetPilot alert rules (pure stdlib; runs in the processor Lambda and in tests).

evaluate(points, device, settings, state, now) -> (alerts, new_state)

  points   cleaned, time-ordered fixes for ONE vehicle (mp91_gold.clean output)
  device   the gold "device" block (last_contact, gps_valid, battery_pct, alarms ...)
  settings the account's alert settings (DEFAULT_SETTINGS merged with what the user saved)
  state    what this vehicle already alerted on (persisted between runs; {} the first time)

Alerts fire on TRANSITIONS only (went offline, entered a geofence, a trip went over the limit),
never repeatedly for a condition that is still true. `state["watermark"]` is the newest fix time
already evaluated, so each fix is looked at once; on the very first run only the last
FIRST_RUN_LOOKBACK_MIN minutes are considered, so switching alerts on doesn't replay history.

Rules (what the MP91 can actually support):
  offline        no message for `offline_minutes` (default 120: a parked MP91 reports ~every 20 min)
  unplugged      tracker reports external power disconnected / removed from power   (device alarm)
  low_battery    vehicle-battery-low alarm, or tracker backup battery <= 20 %
  speeding       a trip exceeds `speed_limit_kmh`; one alert per trip, at its first over-limit fix
  after_hours    ignition on (a trip starts) outside the business hours / days set
  geofence       entering / leaving a circular geofence (per geofence enter/exit switches)
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    ZoneInfo("America/Toronto")
except Exception:  # Lambda images without the tz database: fall back to Eastern time rules
    ZoneInfo = None

FIRST_RUN_LOOKBACK_MIN = 10

DEFAULT_SETTINGS = {
    "enabled": True,
    "offline_minutes": 120,
    "speed_limit_kmh": 110,          # 0 = off
    "after_hours": {"enabled": False, "start": "07:00", "end": "19:00", "days": [0, 1, 2, 3, 4], "tz": "America/Toronto"},
    "low_battery_pct": 20,
    "geofences": [],                 # [{id, name, lat, lon, radius_m, on_enter, on_exit}]
    "email": {"enabled": False, "to": []},
}

SEVERITY = {"offline": "high", "unplugged": "critical", "low_battery": "medium", "speeding": "medium",
            "after_hours": "high", "geofence_enter": "info", "geofence_exit": "info", "back_online": "info"}
CATEGORY = {"offline": "vehicle_offline", "back_online": "vehicle_offline", "unplugged": "unauthorized_movement",
            "low_battery": "low_battery", "speeding": "speeding", "after_hours": "unauthorized_movement",
            "geofence_enter": "geofence", "geofence_exit": "geofence"}


def merged_settings(saved):
    s = {**DEFAULT_SETTINGS, **(saved or {})}
    s["after_hours"] = {**DEFAULT_SETTINGS["after_hours"], **((saved or {}).get("after_hours") or {})}
    s["email"] = {**DEFAULT_SETTINGS["email"], **((saved or {}).get("email") or {})}
    return s


def _t(iso):
    return datetime.fromisoformat(iso)


def _km(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    x = math.sin((lat2 - lat1) * p / 2) ** 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2
    return 12742 * math.asin(math.sqrt(x))


def _eastern(dt_utc):
    """US/Canada Eastern time without a tz database: DST from 2nd Sunday of March 02:00 to 1st Sunday of Nov 02:00."""
    y = dt_utc.year
    mar = datetime(y, 3, 8, tzinfo=timezone.utc); mar += timedelta(days=(6 - mar.weekday()) % 7)
    nov = datetime(y, 11, 1, tzinfo=timezone.utc); nov += timedelta(days=(6 - nov.weekday()) % 7)
    dst = mar + timedelta(hours=7) <= dt_utc < nov + timedelta(hours=6)
    return dt_utc.astimezone(timezone(timedelta(hours=-4 if dst else -5)))


def _local(dt_utc, tz):
    if ZoneInfo is not None:
        try:
            return dt_utc.astimezone(ZoneInfo(tz))
        except Exception:
            pass
    return _eastern(dt_utc)


def _in_hours(dt_utc, ah):
    local = _local(dt_utc, ah.get("tz") or "America/Toronto")
    if local.weekday() not in ah.get("days", [0, 1, 2, 3, 4]):
        return False
    hm = local.strftime("%H:%M")
    start, end = ah.get("start", "07:00"), ah.get("end", "19:00")
    return start <= hm < end if start <= end else (hm >= start or hm < end)  # overnight shifts


def _alert(kind, at, title, message, **extra):
    return {"kind": kind, "category": CATEGORY[kind], "severity": SEVERITY[kind], "time": at, "title": title, "message": message, **extra}


def evaluate(points, device, settings, state, now=None):
    now = now or datetime.now(timezone.utc)
    s = merged_settings(settings)
    st = dict(state or {})
    alerts = []
    if not s.get("enabled", True):
        return alerts, st

    first_run = "watermark" not in st
    floor = (now - timedelta(minutes=FIRST_RUN_LOOKBACK_MIN)).isoformat() if first_run else st["watermark"]
    new_pts = [p for p in points if p["fix_time"] > floor]
    if points:  # the watermark only ever moves with data, never with the clock (late uploads still get evaluated)
        st["watermark"] = max(points[-1]["fix_time"], st.get("watermark", ""))

    # ── device state: offline / unplugged / low battery (fire once per episode, re-arm when cleared) ──
    last = device.get("last_contact") if device else None
    if last:
        silent_min = (now - _t(last)).total_seconds() / 60
        offline = silent_min > s["offline_minutes"]
        if offline and not st.get("offline"):
            alerts.append(_alert("offline", now.isoformat(), "Vehicle not reporting",
                                 f"No message from the tracker for {int(silent_min)} minutes (last at {last})."))
        elif not offline and st.get("offline"):
            alerts.append(_alert("back_online", last, "Vehicle reporting again", "The tracker is sending data again."))
        st["offline"] = offline
    alarms = set((device or {}).get("alarms") or [])
    unplugged = bool(alarms & {"external_power_disconnected", "alarm_battery_removed"})
    if unplugged and not st.get("unplugged"):
        alerts.append(_alert("unplugged", last or now.isoformat(), "Tracker unplugged",
                             "The tracker reports it lost vehicle power. It may have been removed from the OBD port."))
    st["unplugged"] = unplugged
    bpct = (device or {}).get("battery_pct")
    low = "vehicle_battery_low" in alarms or (bpct is not None and bpct <= s["low_battery_pct"])
    if low and not st.get("low_battery"):
        why = "vehicle battery low" if "vehicle_battery_low" in alarms else f"tracker battery at {bpct}%"
        alerts.append(_alert("low_battery", last or now.isoformat(), "Low battery", f"The tracker reports {why}."))
    st["low_battery"] = low

    # ── trip-based: speeding and after-hours (one alert per trip) ──
    trip_start = st.get("trip_start")
    prev_acc = st.get("acc_on", False)
    for p in new_pts:
        acc = bool(p.get("acc_on"))
        if acc and not prev_acc:
            trip_start = p["fix_time"]
            ah = s["after_hours"]
            if ah.get("enabled") and not _in_hours(_t(p["fix_time"]), ah):
                alerts.append(_alert("after_hours", p["fix_time"], "Vehicle used after hours",
                                     f"Ignition on outside business hours ({ah['start']}–{ah['end']}).",
                                     lat=p["latitude"], lon=p["longitude"]))
        if acc and s["speed_limit_kmh"] and p["speed_kmh"] > s["speed_limit_kmh"] and st.get("speeding_trip") != trip_start:
            st["speeding_trip"] = trip_start
            alerts.append(_alert("speeding", p["fix_time"], "Speed limit exceeded",
                                 f"{round(p['speed_kmh'])} km/h (limit {s['speed_limit_kmh']} km/h).",
                                 lat=p["latitude"], lon=p["longitude"], speed_kmh=p["speed_kmh"]))
        prev_acc = acc
    st["acc_on"], st["trip_start"] = prev_acc, trip_start

    # ── geofences: enter / exit transitions ──
    inside = set(st.get("inside", []))
    fences = {g["id"]: g for g in s.get("geofences") or []}
    if first_run and new_pts:  # establish where the vehicle is now without alerting
        p0 = new_pts[0]
        inside = {gid for gid, g in fences.items() if _km(p0["latitude"], p0["longitude"], g["lat"], g["lon"]) * 1000 <= g["radius_m"]}
    for p in new_pts:
        now_in = {gid for gid, g in fences.items() if _km(p["latitude"], p["longitude"], g["lat"], g["lon"]) * 1000 <= g["radius_m"]}
        for gid in now_in - inside:
            if fences[gid].get("on_enter", True):
                alerts.append(_alert("geofence_enter", p["fix_time"], f"Arrived at {fences[gid]['name']}", "Entered geofence.", geofence_id=gid))
        for gid in inside - now_in:
            if gid in fences and fences[gid].get("on_exit", True):
                alerts.append(_alert("geofence_exit", p["fix_time"], f"Left {fences[gid]['name']}", "Exited geofence.", geofence_id=gid))
        inside = now_in
    st["inside"] = sorted(inside & set(fences))
    return alerts, st
