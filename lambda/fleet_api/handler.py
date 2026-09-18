"""
IAP Fleet API — Lambda handler
Routes (via API Gateway HTTP API):
  GET  /data    → return cached dashboard_cache.json from S3 (fast, <100ms)
  GET  /refresh → run Athena queries, rebuild cache, return fresh data (10-30s)
  GET  /health  → liveness check

Environment variables (injected by Terraform):
  LAKE_BUCKET     e.g. iap-dev-lake-313092058964
  ATHENA_DB       e.g. iap_dev_fleet
  ATHENA_TABLE    e.g. telemetry
  ATHENA_WG       e.g. iap-dev-fleet
  RESULTS_BUCKET  e.g. iap-dev-athena-results
  CACHE_KEY       e.g. processed/dashboard_cache.json
"""

import json
import os
import time
import boto3
from datetime import datetime, timezone, timedelta

LAKE_BUCKET    = os.environ["LAKE_BUCKET"]
ATHENA_DB      = os.environ["ATHENA_DB"]
ATHENA_TABLE   = os.environ["ATHENA_TABLE"]
ATHENA_WG      = os.environ["ATHENA_WG"]
RESULTS_BUCKET = os.environ["RESULTS_BUCKET"]
CACHE_KEY      = os.environ.get("CACHE_KEY", "processed/dashboard_cache.json")

s3     = boto3.client("s3")
athena = boto3.client("athena", region_name=os.environ.get("AWS_REGION", "ca-central-1"))

CORS = {
    "Access-Control-Allow-Origin":  "*",
    "Access-Control-Allow-Methods": "GET,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}

# ── Helpers ──────────────────────────────────────────────────────────────────

def resp(status, body, extra_headers=None):
    headers = {**CORS, "Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    return {"statusCode": status, "headers": headers, "body": json.dumps(body)}


def run_athena(sql: str) -> list[dict]:
    """Execute SQL on Athena and return rows as list of dicts. Polls until done."""
    exec_resp = athena.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": ATHENA_DB},
        WorkGroup=ATHENA_WG,
    )
    qid = exec_resp["QueryExecutionId"]

    # Poll
    for _ in range(60):  # max 60s
        time.sleep(1)
        status = athena.get_query_execution(QueryExecutionId=qid)
        state = status["QueryExecution"]["Status"]["State"]
        if state == "SUCCEEDED":
            break
        if state in ("FAILED", "CANCELLED"):
            reason = status["QueryExecution"]["Status"].get("StateChangeReason", "")
            raise RuntimeError(f"Athena query {state}: {reason}")

    # Fetch results (paginated)
    rows = []
    paginator = athena.get_paginator("get_query_results")
    col_names = None
    for page in paginator.paginate(QueryExecutionId=qid):
        result_rows = page["ResultSet"]["Rows"]
        if col_names is None:
            col_names = [c["VarCharValue"] for c in result_rows[0]["Data"]]
            result_rows = result_rows[1:]  # skip header row
        for row in result_rows:
            vals = [c.get("VarCharValue", None) for c in row["Data"]]
            rows.append(dict(zip(col_names, vals)))

    return rows


def safe_float(v, default=None):
    try:
        return float(v) if v not in (None, "", "null") else default
    except (ValueError, TypeError):
        return default


def safe_int(v, default=None):
    try:
        return int(float(v)) if v not in (None, "", "null") else default
    except (ValueError, TypeError):
        return default


def safe_bool(v):
    if isinstance(v, bool):
        return v
    return str(v).lower() in ("true", "1", "yes")


# ── Athena queries ────────────────────────────────────────────────────────────

MSCK = f"MSCK REPAIR TABLE {ATHENA_DB}.{ATHENA_TABLE}"

FLEET_LATEST_SQL = f"""
WITH ranked AS (
  SELECT *,
         ROW_NUMBER() OVER (PARTITION BY vehicle_id ORDER BY timestamp DESC) AS rn
  FROM   {ATHENA_DB}.{ATHENA_TABLE}
)
SELECT vehicle_id,
       timestamp,
       driver_id,
       driver_name,
       speed_kmh,
       heading_deg,
       odometer_km,
       geofence,
       trip_id,
       vehicle_info.make            AS make,
       vehicle_info.model           AS model,
       vehicle_info.year            AS year,
       vehicle_info.type            AS vtype,
       vehicle_info.plate           AS plate,
       location.lat                 AS lat,
       location.lng                 AS lng,
       engine.rpm                   AS rpm,
       engine.temperature_c         AS eng_temp,
       engine.oil_pressure_kpa      AS oil_kpa,
       engine.coolant_temp_c        AS coolant_temp,
       engine.throttle_pct          AS throttle,
       engine.battery_soc_pct       AS battery_soc,
       engine.motor_temp_c          AS motor_temp,
       engine.regen_braking_kw      AS regen_kw,
       engine.power_draw_kw         AS power_kw,
       fuel.level_pct               AS fuel_level,
       fuel.consumption_per_100km   AS consumption,
       fuel.type                    AS fuel_type,
       driver_behavior.harsh_braking     AS harsh_brake,
       driver_behavior.harsh_acceleration AS harsh_accel,
       driver_behavior.speeding          AS speeding,
       driver_behavior.idle_time_s       AS idle_s,
       driver_behavior.safety_score      AS safety_score,
       driver_behavior.seatbelt_on       AS seatbelt,
       driver_behavior.phone_usage       AS phone,
       predictive_maintenance.brake_health        AS brake_health,
       predictive_maintenance.tire_health         AS tire_health,
       predictive_maintenance.oil_change_due_km   AS oil_due_km,
       predictive_maintenance.filter_due_km       AS filter_due_km,
       predictive_maintenance.next_service_days   AS service_days,
       predictive_maintenance.overall_health_score AS health_score,
       network.signal_strength      AS signal,
       network.protocol             AS protocol
FROM   ranked
WHERE  rn = 1
ORDER  BY vehicle_id
"""

HOURLY_AGG_SQL = f"""
SELECT vehicle_id,
       date_trunc('hour', from_iso8601_timestamp(timestamp)) AS hour,
       COUNT(*)                                              AS records,
       AVG(speed_kmh)                                        AS avg_speed,
       AVG(driver_behavior.safety_score)                     AS avg_safety_score,
       AVG(fuel.level_pct)                                   AS fuel_level,
       SUM(CASE WHEN driver_behavior.harsh_braking  THEN 1 ELSE 0 END) AS harsh_brakes,
       SUM(CASE WHEN driver_behavior.harsh_acceleration THEN 1 ELSE 0 END) AS harsh_accels,
       SUM(CASE WHEN driver_behavior.speeding       THEN 1 ELSE 0 END) AS speeding_events,
       SUM(CASE WHEN CARDINALITY(fault_codes) > 0  THEN 1 ELSE 0 END) AS fault_events
FROM   {ATHENA_DB}.{ATHENA_TABLE}
WHERE  from_iso8601_timestamp(timestamp) >= NOW() - INTERVAL '41' HOUR
GROUP  BY 1, 2
ORDER  BY 1, 2
"""

KPI_SQL = f"""
WITH latest AS (
  SELECT vehicle_id, MAX(timestamp) AS ts
  FROM   {ATHENA_DB}.{ATHENA_TABLE}
  GROUP  BY vehicle_id
),
fleet AS (
  SELECT t.vehicle_id,
         t.speed_kmh,
         t.fuel.level_pct        AS fuel_pct,
         t.driver_behavior.safety_score AS safety,
         t.fault_codes,
         t.engine.battery_soc_pct AS battery_soc
  FROM   {ATHENA_DB}.{ATHENA_TABLE} t
  JOIN   latest l ON t.vehicle_id = l.vehicle_id AND t.timestamp = l.ts
)
SELECT
  COUNT(*)                                              AS total_vehicles,
  SUM(CASE WHEN speed_kmh > 5 THEN 1 ELSE 0 END)       AS active_vehicles,
  SUM(CASE WHEN speed_kmh <= 5 THEN 1 ELSE 0 END)       AS idle_vehicles,
  ROUND(AVG(safety), 1)                                 AS avg_safety_score,
  SUM(CASE WHEN CARDINALITY(fault_codes) > 0 THEN 1 ELSE 0 END) AS total_active_faults,
  SUM(CASE WHEN fuel_pct < 20 AND battery_soc IS NULL THEN 1 ELSE 0 END) AS low_fuel_vehicles,
  SUM(CASE WHEN battery_soc IS NOT NULL THEN 1 ELSE 0 END) AS ev_vehicles,
  ROUND(AVG(fuel_pct), 1)                               AS avg_fuel_level
FROM fleet
"""


# ── Shape raw Athena rows into dashboard JSON format ─────────────────────────

def shape_fleet_latest(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        is_ev = r.get("battery_soc") not in (None, "")
        out.append({
            "vehicle_id":   r["vehicle_id"],
            "timestamp":    r["timestamp"],
            "driver_id":    r.get("driver_id"),
            "driver_name":  r.get("driver_name"),
            "speed_kmh":    safe_float(r.get("speed_kmh"), 0),
            "heading_deg":  safe_float(r.get("heading_deg"), 0),
            "odometer_km":  safe_float(r.get("odometer_km"), 0),
            "geofence":     r.get("geofence", ""),
            "trip_id":      r.get("trip_id"),
            "vehicle_info": {
                "make":  r.get("make", ""),
                "model": r.get("model", ""),
                "year":  safe_int(r.get("year")),
                "type":  r.get("vtype", ""),
                "plate": r.get("plate", ""),
                "vin":   "",
            },
            "location": {
                "lat": safe_float(r.get("lat"), 43.7),
                "lng": safe_float(r.get("lng"), -79.4),
                "altitude": 0,
                "accuracy": 3,
            },
            "engine": {
                "rpm":             safe_float(r.get("rpm")),
                "temperature_c":   safe_float(r.get("eng_temp")),
                "oil_pressure_kpa": safe_float(r.get("oil_kpa")),
                "coolant_temp_c":  safe_float(r.get("coolant_temp")),
                "throttle_pct":    safe_float(r.get("throttle")),
                "battery_soc_pct": safe_float(r.get("battery_soc")),
                "motor_temp_c":    safe_float(r.get("motor_temp")),
                "regen_braking_kw": safe_float(r.get("regen_kw")),
                "power_draw_kw":   safe_float(r.get("power_kw")),
            },
            "fuel": {
                "level_pct":            safe_float(r.get("fuel_level"), 50),
                "consumption_per_100km": safe_float(r.get("consumption")),
                "type":                 r.get("fuel_type", "gasoline"),
                "kwh_consumed":         None,
            },
            "driver_behavior": {
                "harsh_braking":      safe_bool(r.get("harsh_brake")),
                "harsh_acceleration": safe_bool(r.get("harsh_accel")),
                "speeding":           safe_bool(r.get("speeding")),
                "idle_time_s":        safe_float(r.get("idle_s"), 0),
                "safety_score":       safe_float(r.get("safety_score"), 85),
                "seatbelt_on":        safe_bool(r.get("seatbelt")),
                "phone_usage":        safe_bool(r.get("phone")),
            },
            "predictive_maintenance": {
                "brake_health":        safe_float(r.get("brake_health"), 80),
                "tire_health":         safe_float(r.get("tire_health"), 80),
                "oil_change_due_km":   safe_float(r.get("oil_due_km"), 5000),
                "filter_due_km":       safe_float(r.get("filter_due_km"), 8000),
                "next_service_days":   safe_int(r.get("service_days"), 30),
                "overall_health_score": safe_float(r.get("health_score"), 80),
            },
            "fault_codes": [],   # fault_codes array not easily fetchable via flat SQL; enriched separately
            "network": {
                "signal_strength": safe_float(r.get("signal"), -80),
                "protocol":        r.get("protocol", "4G"),
            },
        })
    return out


def shape_hourly_agg(rows: list[dict]) -> dict:
    """Returns {vehicle_id: [hourly records...]}"""
    agg: dict = {}
    for r in rows:
        vid = r["vehicle_id"]
        if vid not in agg:
            agg[vid] = []
        agg[vid].append({
            "hour":             r["hour"],
            "records":          safe_int(r.get("records"), 0),
            "avg_speed":        safe_float(r.get("avg_speed"), 0),
            "avg_safety_score": safe_float(r.get("avg_safety_score"), 85),
            "fuel_level":       safe_float(r.get("fuel_level"), 50),
            "harsh_brakes":     safe_int(r.get("harsh_brakes"), 0),
            "harsh_accels":     safe_int(r.get("harsh_accels"), 0),
            "speeding_events":  safe_int(r.get("speeding_events"), 0),
            "fault_events":     safe_int(r.get("fault_events"), 0),
        })
    return agg


def shape_kpis(rows: list[dict]) -> dict:
    r = rows[0] if rows else {}
    return {
        "total_vehicles":     safe_int(r.get("total_vehicles"), 0),
        "active_vehicles":    safe_int(r.get("active_vehicles"), 0),
        "idle_vehicles":      safe_int(r.get("idle_vehicles"), 0),
        "avg_safety_score":   safe_float(r.get("avg_safety_score"), 0),
        "total_active_faults": safe_int(r.get("total_active_faults"), 0),
        "low_fuel_vehicles":  safe_int(r.get("low_fuel_vehicles"), 0),
        "ev_vehicles":        safe_int(r.get("ev_vehicles"), 0),
        "avg_fuel_level":     safe_float(r.get("avg_fuel_level"), 0),
    }


# ── Route handlers ────────────────────────────────────────────────────────────

def handle_health():
    return resp(200, {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()})


def handle_data():
    """Return cached dashboard data from S3."""
    try:
        obj = s3.get_object(Bucket=LAKE_BUCKET, Key=CACHE_KEY)
        data = json.loads(obj["Body"].read())
        last_modified = obj["LastModified"].isoformat()
        return resp(200, {**data, "cache_updated_at": last_modified})
    except s3.exceptions.NoSuchKey:
        return resp(404, {
            "error": "Cache not built yet. Call GET /refresh first.",
            "hint": "Run: curl -X GET '<api_url>/refresh'"
        })
    except Exception as e:
        return resp(500, {"error": str(e)})


def handle_refresh():
    """Run Athena queries, update S3 cache, return fresh data."""
    try:
        started = time.time()

        # 1. Repair partitions so new uploads are visible
        try:
            run_athena(MSCK)
        except Exception:
            pass  # non-fatal; may already be repaired

        # 2. Run the three queries (sequential — Athena free tier friendly)
        fleet_rows  = run_athena(FLEET_LATEST_SQL)
        hourly_rows = run_athena(HOURLY_AGG_SQL)
        kpi_rows    = run_athena(KPI_SQL)

        # 3. Shape into dashboard format
        payload = {
            "fleet_latest": shape_fleet_latest(fleet_rows),
            "hourly_agg":   shape_hourly_agg(hourly_rows),
            "kpis":         shape_kpis(kpi_rows),
            "refreshed_at": datetime.now(timezone.utc).isoformat(),
            "query_time_s": round(time.time() - started, 1),
        }

        # 4. Write to S3 cache
        s3.put_object(
            Bucket=LAKE_BUCKET,
            Key=CACHE_KEY,
            Body=json.dumps(payload, default=str),
            ContentType="application/json",
            ServerSideEncryption="AES256",
        )

        return resp(200, payload, {"X-Query-Time": str(payload["query_time_s"])})

    except Exception as e:
        return resp(500, {"error": str(e)})


# ── Lambda entry point ────────────────────────────────────────────────────────

def lambda_handler(event, context):
    method  = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    path    = event.get("rawPath", "/data").rstrip("/") or "/data"

    # OPTIONS preflight
    if method == "OPTIONS":
        return {"statusCode": 204, "headers": CORS, "body": ""}

    if path == "/health":
        return handle_health()
    if path == "/refresh":
        return handle_refresh()
    # Default: /data
    return handle_data()
