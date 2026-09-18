"""
Industrial AI Platform — Vehicle Telemetry Data Generator
Generates 7 days of realistic telemetry for 20 vehicles across Ontario, Canada.
Output: JSONL files partitioned by year/month/day under data/raw/telemetry/
"""

import json
import math
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

random.seed(42)

# ---------------------------------------------------------------------------
# Fleet configuration
# ---------------------------------------------------------------------------
VEHICLES = [
    {"id": f"VH-{i:03d}", "make": m, "model": mo, "year": y, "type": t,
     "driver_id": f"DRV-{i:03d}", "driver_name": dn, "plate": f"IAP-{i:04d}",
     "odometer_base": random.randint(15000, 120000)}
    for i, (m, mo, y, t, dn) in enumerate([
        ("Ford",       "Transit",      2022, "Van",   "James Wilson"),
        ("Ford",       "Transit",      2023, "Van",   "Maria Santos"),
        ("Mercedes",   "Sprinter",     2021, "Van",   "David Chen"),
        ("Mercedes",   "Sprinter",     2022, "Van",   "Priya Patel"),
        ("RAM",        "ProMaster",    2023, "Van",   "Ahmed Hassan"),
        ("Freightliner","Cascadia",    2020, "Truck", "Robert Kim"),
        ("Kenworth",   "T680",         2021, "Truck", "Lisa Thompson"),
        ("Volvo",      "VNL",          2022, "Truck", "Carlos Rivera"),
        ("Peterbilt",  "579",          2019, "Truck", "Emma Clarke"),
        ("International","LT",         2021, "Truck", "Noah Martin"),
        ("Ford",       "F-150",        2023, "Pickup","Sophie Lee"),
        ("Chevrolet",  "Silverado",    2022, "Pickup","Jack Brown"),
        ("RAM",        "1500",         2021, "Pickup","Olivia Davis"),
        ("Toyota",     "Tundra",       2023, "Pickup","Liam Anderson"),
        ("GMC",        "Sierra",       2022, "Pickup","Ava Taylor"),
        ("Ford",       "E-Transit",    2023, "EV Van","Ethan White"),
        ("Mercedes",   "eSprinter",    2022, "EV Van","Mia Jackson"),
        ("Rivian",     "EDV",          2023, "EV Van","Lucas Garcia"),
        ("Ford",       "F-150 Lightning",2023,"EV Pickup","Isabella Moore"),
        ("Chevrolet",  "Silverado EV", 2023, "EV Pickup","William Harris"),
    ], start=1)
]

# Ontario waypoints (realistic route segments)
ROUTES = [
    # Toronto → Ottawa
    [(43.6532, -79.3832), (43.8971, -78.8658), (44.1483, -78.1661),
     (44.3597, -77.6162), (44.5801, -77.0094), (45.0853, -76.3543),
     (45.4215, -75.6972)],
    # Toronto → Windsor
    [(43.6532, -79.3832), (43.2557, -79.8711), (43.1594, -80.2527),
     (43.0896, -81.2762), (42.9849, -81.9999), (42.3149, -83.0364)],
    # Toronto → Barrie
    [(43.6532, -79.3832), (43.8553, -79.5345), (44.0714, -79.6718),
     (44.3894, -79.6900)],
    # Toronto → Kingston
    [(43.6532, -79.3832), (43.9273, -78.6774), (44.0742, -77.5869),
     (44.2312, -76.4818)],
    # Ottawa → Sudbury
    [(45.4215, -75.6972), (45.5017, -76.0886), (46.3091, -79.4608),
     (46.4877, -80.9953)],
]

FAULT_CODES = [
    ("P0300", "Random/Multiple Cylinder Misfire", "medium"),
    ("P0171", "System Too Lean (Bank 1)", "low"),
    ("P0420", "Catalyst System Efficiency Below Threshold", "low"),
    ("P0401", "Exhaust Gas Recirculation Flow Insufficient", "low"),
    ("P0507", "Idle Control System RPM High", "low"),
    ("P0128", "Coolant Temperature Below Thermostat Regulating Temperature", "low"),
    ("P0455", "Evaporative Emission System Leak Detected (Large)", "medium"),
    ("B0001", "Airbag Deployment Loop Open", "critical"),
    ("U0100", "Lost Communication With ECM/PCM", "critical"),
    ("C0040", "Right Front Wheel Speed Sensor Circuit", "medium"),
]

GEOFENCES = [
    "zone-toronto-depot", "zone-ottawa-depot", "zone-windsor-depot",
    "zone-highway-401", "zone-highway-400", "zone-highway-417",
    "zone-customer-north", "zone-customer-east", "zone-customer-west",
    "zone-restricted", "zone-service-area",
]

def interpolate_route(route, steps):
    """Generate smooth GPS points along a route segment."""
    points = []
    seg_steps = max(1, steps // (len(route) - 1))
    for i in range(len(route) - 1):
        a, b = route[i], route[i+1]
        for s in range(seg_steps):
            t = s / seg_steps
            lat = a[0] + (b[0] - a[0]) * t + random.gauss(0, 0.002)
            lng = a[1] + (b[1] - a[1]) * t + random.gauss(0, 0.002)
            points.append((round(lat, 6), round(lng, 6)))
    return points

def generate_telemetry(vehicle, timestamp, prev=None, route_pts=None, step=0, is_ev=False):
    """Generate one telemetry event for a vehicle."""
    in_trip = route_pts is not None

    # Location
    if in_trip and step < len(route_pts):
        lat, lng = route_pts[step]
    elif prev:
        lat = prev["location"]["lat"] + random.gauss(0, 0.0001)
        lng = prev["location"]["lng"] + random.gauss(0, 0.0001)
    else:
        base = random.choice(ROUTES)[0]
        lat = base[0] + random.gauss(0, 0.01)
        lng = base[1] + random.gauss(0, 0.01)

    # Speed
    if in_trip:
        speed = random.gauss(85, 15) if "highway" in GEOFENCES[step % len(GEOFENCES)] else random.gauss(45, 10)
        speed = max(0, min(speed, 130))
    elif prev and prev["speed_kmh"] > 0:
        speed = max(0, prev["speed_kmh"] + random.gauss(0, 5))
    else:
        speed = 0

    # Engine / battery
    if is_ev:
        engine = {
            "battery_soc_pct": round(max(5, min(100, (prev["engine"]["battery_soc_pct"] - random.uniform(0.05, 0.3)) if prev else random.uniform(40, 95))), 1),
            "motor_temp_c": round(random.gauss(45, 8), 1),
            "regen_braking_kw": round(random.uniform(0, 40) if speed > 20 else 0, 1),
            "power_draw_kw": round(random.uniform(10, 80) if speed > 0 else random.uniform(0.5, 2), 1),
            "charging": False,
            "rpm": 0,
            "temperature_c": None,
            "oil_pressure_kpa": None,
            "coolant_temp_c": None,
            "throttle_pct": round(random.uniform(0, 80) if speed > 0 else 0, 1),
        }
        fuel = {"level_pct": engine["battery_soc_pct"], "consumption_per_100km": None,
                "type": "electric", "kwh_consumed": round(engine["power_draw_kw"] * (5/60), 2)}
    else:
        rpm = int(random.gauss(2200, 300) if speed > 10 else random.gauss(750, 50))
        rpm = max(600, min(rpm, 4500))
        engine = {
            "rpm": rpm,
            "temperature_c": round(random.gauss(92, 3), 1),
            "oil_pressure_kpa": round(random.gauss(275, 15), 1),
            "coolant_temp_c": round(random.gauss(88, 4), 1),
            "throttle_pct": round(random.uniform(0, 90) if speed > 0 else 0, 1),
            "battery_soc_pct": None,
            "motor_temp_c": None,
            "regen_braking_kw": None,
            "power_draw_kw": None,
            "charging": None,
        }
        prev_fuel = prev["fuel"]["level_pct"] if prev else random.uniform(40, 95)
        consumption = random.gauss(8.5, 1.5) if speed > 0 else 0.3
        fuel_used = consumption * speed * (5/60) / 100
        fuel = {
            "level_pct": round(max(2, prev_fuel - fuel_used * 2), 1),
            "consumption_per_100km": round(consumption, 2),
            "type": "diesel" if vehicle["type"] == "Truck" else "gasoline",
            "kwh_consumed": None,
        }

    # Driver behavior
    harsh_brake = random.random() < 0.02
    harsh_accel = random.random() < 0.015
    speeding = speed > 110
    idle_secs = random.randint(0, 300) if speed == 0 else 0
    safety_score = 100 - (harsh_brake * 5) - (harsh_accel * 3) - (speeding * 8) - (idle_secs > 180) * 2

    # Fault codes (rare)
    active_faults = []
    if random.random() < 0.008:
        code = random.choice(FAULT_CODES)
        active_faults = [{"code": code[0], "description": code[1], "severity": code[2],
                           "first_seen": timestamp.isoformat()}]

    # Predictive maintenance scores (0-100, lower = needs attention sooner)
    odo = vehicle["odometer_base"] + step * 0.5
    maint = {
        "brake_health": round(max(10, 100 - (odo % 30000) / 300), 1),
        "tire_health": round(max(15, 100 - (odo % 15000) / 150), 1),
        "oil_change_due_km": max(0, 8000 - (odo % 8000)),
        "filter_due_km": max(0, 20000 - (odo % 20000)),
        "next_service_days": max(0, 90 - (step % 90)),
        "overall_health_score": round(random.gauss(82, 8), 1),
    }

    geofence = GEOFENCES[step % len(GEOFENCES)]
    trip_id = f"TRIP-{vehicle['id']}-{timestamp.strftime('%Y%m%d')}" if in_trip else None

    return {
        "event_id": str(uuid.uuid4()),
        "timestamp": timestamp.isoformat(),
        "vehicle_id": vehicle["id"],
        "vehicle_info": {
            "make": vehicle["make"],
            "model": vehicle["model"],
            "year": vehicle["year"],
            "type": vehicle["type"],
            "plate": vehicle["plate"],
        },
        "driver_id": vehicle["driver_id"],
        "driver_name": vehicle["driver_name"],
        "location": {
            "lat": round(lat, 6),
            "lng": round(lng, 6),
            "altitude_m": round(random.gauss(150, 30), 1),
            "accuracy_m": round(random.uniform(2, 8), 1),
        },
        "speed_kmh": round(speed, 1),
        "heading_deg": round(random.uniform(0, 360), 1),
        "odometer_km": round(odo, 1),
        "engine": engine,
        "fuel": fuel,
        "driver_behavior": {
            "harsh_braking": harsh_brake,
            "harsh_acceleration": harsh_accel,
            "speeding": speeding,
            "idle_time_s": idle_secs,
            "safety_score": round(safety_score, 1),
            "seatbelt_on": random.random() > 0.02,
            "phone_usage": random.random() < 0.01,
        },
        "predictive_maintenance": maint,
        "fault_codes": active_faults,
        "geofence": geofence,
        "trip_id": trip_id,
        "network": {
            "signal_strength": random.randint(-100, -50),
            "protocol": random.choice(["4G", "4G", "4G", "5G", "3G"]),
        },
        "schema_version": "1.2",
        "source": "simulator_v2",
    }

def main():
    output_base = Path(__file__).parent.parent / "data" / "raw" / "telemetry"
    output_base.mkdir(parents=True, exist_ok=True)

    end_dt = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    start_dt = end_dt - timedelta(days=7)

    print(f"Generating telemetry: {start_dt.date()} → {end_dt.date()}")
    print(f"Fleet: {len(VEHICLES)} vehicles | Interval: 5 min | Total events: ~{len(VEHICLES) * 7 * 24 * 12:,}")

    # Group records by date for partitioned output
    by_date: dict = {}
    total = 0

    for vehicle in VEHICLES:
        print(f"  Simulating {vehicle['id']} ({vehicle['make']} {vehicle['model']})...")
        is_ev = "EV" in vehicle["type"]
        prev = None
        step = 0

        # Build trip schedule: 2-3 trips per day
        trips = []
        day = start_dt
        while day < end_dt:
            num_trips = random.randint(1, 3)
            for _ in range(num_trips):
                trip_start_h = random.randint(6, 20)
                trip_dur_h = random.randint(1, 5)
                trips.append((
                    day.replace(hour=trip_start_h, minute=0),
                    day.replace(hour=min(23, trip_start_h + trip_dur_h), minute=0),
                    random.choice(ROUTES),
                ))
            day += timedelta(days=1)

        cur = start_dt
        trip_idx = 0
        while cur < end_dt:
            # Determine if in a trip
            in_trip = False
            route_pts = None
            if trip_idx < len(trips):
                ts, te, route = trips[trip_idx]
                if ts <= cur <= te:
                    in_trip = True
                    trip_steps = int((te - ts).total_seconds() / 300)
                    elapsed = int((cur - ts).total_seconds() / 300)
                    route_pts = interpolate_route(route, trip_steps)
                elif cur > te:
                    trip_idx += 1

            event = generate_telemetry(vehicle, cur, prev, route_pts if in_trip else None, step, is_ev)
            prev = event
            step += 1

            date_key = cur.strftime("%Y/%m/%d")
            if date_key not in by_date:
                by_date[date_key] = []
            by_date[date_key].append(event)
            total += 1

            cur += timedelta(minutes=5)

    # Write partitioned JSONL files
    for date_key, events in sorted(by_date.items()):
        year, month, day = date_key.split("/")
        out_dir = output_base / f"year={year}" / f"month={month}" / f"day={day}"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "telemetry.jsonl"
        with open(out_file, "w") as f:
            for e in events:
                f.write(json.dumps(e) + "\n")
        print(f"  Wrote {len(events):,} events → {out_file.relative_to(output_base.parent.parent.parent)}")

    print(f"\nDone! {total:,} total events across {len(by_date)} days.")
    print(f"Output: {output_base}")

    # Also write a summary JSON for the dashboard
    summary_dir = Path(__file__).parent.parent / "data"
    summary_dir.mkdir(exist_ok=True)

    # Read last day's data for dashboard seed
    last_key = sorted(by_date.keys())[-1]
    latest_events = by_date[last_key]
    # Latest event per vehicle
    latest_by_vehicle = {}
    for e in latest_events:
        latest_by_vehicle[e["vehicle_id"]] = e

    with open(summary_dir / "fleet_latest.json", "w") as f:
        json.dump(list(latest_by_vehicle.values()), f, indent=2)

    # Write full last 24h for dashboard charts
    last_2_keys = sorted(by_date.keys())[-2:]
    last_24h = []
    for k in last_2_keys:
        last_24h.extend(by_date[k])
    with open(summary_dir / "telemetry_24h.json", "w") as f:
        json.dump(last_24h, f, indent=2)

    print(f"Dashboard seed data written to data/fleet_latest.json and data/telemetry_24h.json")

if __name__ == "__main__":
    main()
