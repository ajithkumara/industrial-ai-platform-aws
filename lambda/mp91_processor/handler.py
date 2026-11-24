"""MP91 tracking Lambda — two entry points in one package.

process(event, ctx)  — runs every minute (EventBridge). For today + yesterday
    (UTC) it lists raw/mp91/ bronze files, parses only the ones not yet
    processed, merges them into the silver day file, then rebuilds
    each account's gold file from the last GOLD_DAYS silver day files.
    A schedule (not S3 events) means no concurrent writers to the day file,
    and any file missed for any reason is picked up on the next run.

api(event, ctx)      — GET /mp91 behind the Cognito JWT authorizer. Looks up the
    caller's account (USER#<cognito sub>) and returns that account's gold file.

Accounts (multi-tenant) live in one DynamoDB table (FLEET_TABLE), single-table design:
  PK ACCOUNT#<aid>  SK META             name, kind (fleet|personal), plan
  PK ACCOUNT#<aid>  SK VEHICLE#<vid>    name, plate, device_id, driver
  PK DEVICE#<id>    SK META             account_id, vehicle_id   (device -> owner lookup)
  PK USER#<sub>     SK META             account_id, email, role  (login -> account lookup)
An individual owner is an account with kind=personal and one vehicle.
Devices not registered to any account are processed but published to no one.

Layout in the lake bucket:
  raw/mp91/year=YYYY/month=MM/day=DD/*.jsonl      bronze (edge listener)
  silver/mp91/days/YYYY-MM-DD.json                {"processed": [...keys], "records": [...]}
  quarantine/mp91/YYYY-MM-DD.jsonl                unparseable frames (latest run's rejects appended)
  gold/accounts/<aid>/latest.json                 per-account vehicles, routes, trips, parking
"""
import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import boto3
from botocore.exceptions import ClientError

from h02_parser import parse_bronze_event
from mp91_gold import build, clean
from mp91_alerts import evaluate, merged_settings

S3 = boto3.client("s3")
BUCKET = os.environ["LAKE_BUCKET"]
GOLD_DAYS = int(os.environ.get("GOLD_DAYS", "7"))
TABLE = boto3.resource("dynamodb").Table(os.environ["FLEET_TABLE"])


def _get_json(key, default):
    try:
        return json.loads(S3.get_object(Bucket=BUCKET, Key=key)["Body"].read())
    except ClientError as e:
        if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
            return default
        raise


def _put_json(key, obj):
    S3.put_object(Bucket=BUCKET, Key=key, Body=json.dumps(obj, separators=(",", ":")).encode(),
                  ContentType="application/json")


def _list(prefix):
    keys, token = [], None
    while True:
        kw = {"Bucket": BUCKET, "Prefix": prefix}
        if token:
            kw["ContinuationToken"] = token
        r = S3.list_objects_v2(**kw)
        keys += [o["Key"] for o in r.get("Contents", []) if o["Key"].endswith(".jsonl")]
        if not r.get("IsTruncated"):
            return keys
        token = r["NextContinuationToken"]


def _process_day(day):
    raw_prefix = f"raw/mp91/year={day:%Y}/month={day:%m}/day={day:%d}/"
    silver_key = f"silver/mp91/days/{day:%Y-%m-%d}.json"
    state = _get_json(silver_key, {"processed": [], "records": []})
    done = set(state["processed"])
    new_keys = [k for k in _list(raw_prefix) if k not in done]
    if not new_keys:
        return 0
    by_id = {r["record_id"]: r for r in state["records"]}
    rejects = []
    for key in new_keys:
        body = S3.get_object(Bucket=BUCKET, Key=key)["Body"].read().decode("utf-8")
        for line in body.splitlines():
            if line.strip():
                recs, rej = parse_bronze_event(json.loads(line))
                for r in recs:
                    by_id[r["record_id"]] = r
                rejects += [{**x, "source_key": key} for x in rej]
    state["processed"] = sorted(done | set(new_keys))
    state["records"] = sorted(by_id.values(), key=lambda r: r["fix_time"])
    _put_json(silver_key, state)
    if rejects:
        qkey = f"quarantine/mp91/{day:%Y-%m-%d}/{datetime.now(timezone.utc):%H%M%S}.jsonl"
        S3.put_object(Bucket=BUCKET, Key=qkey, Body="\n".join(json.dumps(r) for r in rejects).encode())
    print(json.dumps({"day": f"{day:%Y-%m-%d}", "new_files": len(new_keys),
                      "records": len(state["records"]), "rejects": len(rejects)}))
    return len(new_keys)


PASSES = int(os.environ.get("PASSES", "1"))                  # passes per invocation (EventBridge minimum is 1/min)
PASS_SECONDS = int(os.environ.get("PASS_SECONDS", "15"))     # spacing between passes


def process(event, context):
    """One scheduled invocation = PASSES passes PASS_SECONDS apart, so fresh data is published
    every ~15 s instead of every 60 s. Stops early if the invocation is about to time out."""
    result = _process_once(event, context)
    try:
        result["swept_alerts"] = sweep_device_alerts()   # once per invocation (= once a minute)
    except Exception as e:
        print(json.dumps({"sweep_error": str(e)}))
    for _ in range(PASSES - 1):
        if context is not None and context.get_remaining_time_in_millis() < (PASS_SECONDS + 12) * 1000:
            break
        time.sleep(PASS_SECONDS)
        result = _process_once(event, context)
    return result


BACKLOG_DAYS = int(os.environ.get("BACKLOG_DAYS", "7"))      # hourly sweep window for late raw files


def _days_to_scan(now, event):
    """Today and yesterday on every pass. Once an hour (and on demand with {"backlog": true}) also
    sweep the last BACKLOG_DAYS, so files uploaded late (edge server down, tracker offline for days)
    are never skipped. Hourly keeps S3 LIST requests (and cost) flat."""
    hourly = now.minute == 0 and now.second < PASS_SECONDS
    days = BACKLOG_DAYS if (hourly or event.get("backlog") is True) else 2
    return [now.date() - timedelta(days=d) for d in range(days - 1, -1, -1)]


def _process_once(event, context):
    now = datetime.now(timezone.utc)
    today = now.date()
    changed = sum(_process_day(day) for day in _days_to_scan(now, event))
    if not changed and event.get("force") is not True:
        return {"changed": 0}
    records = []
    for d in range(GOLD_DAYS - 1, -1, -1):
        day = today - timedelta(days=d)
        records += _get_json(f"silver/mp91/days/{day:%Y-%m-%d}.json", {"records": []})["records"]
    return publish_accounts(records, changed)


def _accounts():
    """{account_id: {"meta": {...}, "vehicles": [...]}} from the fleet table (small; one scan)."""
    items, kw = [], {}
    while True:
        r = TABLE.scan(**kw)
        items += r["Items"]
        if "LastEvaluatedKey" not in r:
            break
        kw["ExclusiveStartKey"] = r["LastEvaluatedKey"]
    acc = {}
    for it in items:
        if not it["PK"].startswith("ACCOUNT#"):
            continue
        a = acc.setdefault(it["PK"][8:], {"meta": {}, "vehicles": []})
        if it["SK"] == "META":
            a["meta"] = it
        elif it["SK"] == "ALERTSETTINGS":
            a["alert_settings"] = json.loads(it.get("settings", "{}"))
        elif it["SK"].startswith("VEHICLE#"):
            a["vehicles"].append(it)
    return acc


def publish_accounts(records, changed=0):
    now = datetime.now(timezone.utc).isoformat()
    published = 0
    for aid, a in _accounts().items():
        vehicles, new_alerts = [], []
        settings = a.get("alert_settings")
        for v in sorted(a["vehicles"], key=lambda v: v.get("name", "")):
            g = build(records, device_id=v["device_id"])
            g.update(vehicle_id=v["SK"][8:], name=v.get("name", v["device_id"]),
                     plate=v.get("plate"), driver=v.get("driver"))
            vehicles.append(g)
            try:
                pts = clean([r for r in records if r.get("device_id") == v["device_id"]])
                new_alerts += run_alerts(aid, v, pts, g.get("device"), settings)
            except Exception as e:  # alerts must never break publishing
                print(json.dumps({"alert_error": str(e), "account": aid, "vehicle": v["SK"]}))
        email_alerts(aid, settings, new_alerts)
        _put_json(f"gold/accounts/{aid}/latest.json", {
            "account_id": aid, "account_name": a["meta"].get("name", aid),
            "kind": a["meta"].get("kind", "fleet"), "generated_at": now, "vehicles": vehicles})
        published += 1
    return {"changed": changed, "accounts": published}


# ── Alerts ─────────────────────────────────────────────────────────────────────
# PK ACCOUNT#<aid> SK ALERTSETTINGS       settings (JSON string) saved from the app
# PK ACCOUNT#<aid> SK ALERT#<time>#<id>   one alert; kept 90 days (ttl)
# PK DEVICE#<id>   SK ALERTSTATE          what was already alerted (transitions only)
ALERT_TTL_DAYS = 90


def run_alerts(aid, v, points, device, settings, now=None):
    dev = v["device_id"]
    key = {"PK": f"DEVICE#{dev}", "SK": "ALERTSTATE"}
    old = TABLE.get_item(Key=key).get("Item")
    state = json.loads(old["state"]) if old else {}
    alerts, new_state = evaluate(points, device, settings, state, now)
    for al in alerts:
        aid_ = uuid.uuid4().hex[:8]
        TABLE.put_item(Item={"PK": f"ACCOUNT#{aid}", "SK": f"ALERT#{al['time']}#{aid_}", "id": aid_,
                             "vehicle_id": v["SK"][8:], "vehicle_name": v.get("name", dev), "device_id": dev,
                             "alert": json.dumps(al, default=str), "emailed": False,
                             "ttl": int(time.time()) + ALERT_TTL_DAYS * 86400})
    if new_state != state:
        TABLE.put_item(Item={**key, "state": json.dumps(new_state)})
    return [{**al, "vehicle_name": v.get("name", dev)} for al in alerts]


def sweep_device_alerts():
    """Once a minute: re-check time-based conditions (offline) even when no new data arrived,
    from the device block in each account's gold file. No points = trips/geofences untouched."""
    n = 0
    for aid, a in _accounts().items():
        gold = _get_json(f"gold/accounts/{aid}/latest.json", None)
        if not gold:
            continue
        byv = {g["vehicle_id"]: g for g in gold.get("vehicles", [])}
        fired = []
        for v in a["vehicles"]:
            g = byv.get(v["SK"][8:])
            if g and g.get("device"):
                fired += run_alerts(aid, v, [], g["device"], a.get("alert_settings"))
        email_alerts(aid, a.get("alert_settings"), fired)
        n += len(fired)
    return n


# ── Alert email (SES) ──────────────────────────────────────────────────────────
ALERT_EMAIL_FROM = os.environ.get("ALERT_EMAIL_FROM", "")
APP_URL = os.environ.get("APP_URL", "")
EMAIL_MAX_PER_HOUR = int(os.environ.get("EMAIL_MAX_PER_HOUR", "10"))   # per account: a flapping device can't flood an inbox
_ses = None


def _local_time(iso):
    from mp91_alerts import _local
    try:
        return _local(datetime.fromisoformat(iso), "America/Toronto").strftime("%a %d %b %H:%M")
    except Exception:
        return iso


def email_alerts(aid, settings, alerts):
    """One digest email per account per processing pass, if the account turned email on.
    Returns the number of emails sent (0 or 1). Never raises: email must not break processing."""
    global _ses
    s = merged_settings(settings)
    to = s["email"]["to"]
    if not alerts or not ALERT_EMAIL_FROM or not s["email"]["enabled"] or not to:
        return 0
    try:
        hour = datetime.now(timezone.utc).strftime("%Y%m%d%H")
        key = {"PK": f"ACCOUNT#{aid}", "SK": "EMAILRATE"}
        rate = TABLE.get_item(Key=key).get("Item") or {}
        sent = int(rate.get("count", 0)) if rate.get("hour") == hour else 0
        if sent >= EMAIL_MAX_PER_HOUR:
            print(json.dumps({"email_suppressed": len(alerts), "account": aid, "reason": "hourly limit"}))
            return 0
        TABLE.put_item(Item={**key, "hour": hour, "count": sent + 1, "ttl": int(time.time()) + 7200})
        first = alerts[0]
        subject = (f"FleetPilot: {first['vehicle_name']} - {first['title']}" if len(alerts) == 1
                   else f"FleetPilot: {len(alerts)} new alerts")
        lines = [f"- {_local_time(al['time'])}  {al['vehicle_name']}: {al['title']}. {al['message']}" for al in alerts]
        link = f"{APP_URL}/#/notifications" if APP_URL else ""
        body = "\n".join(["New FleetPilot alerts:", "", *lines, "", f"Open FleetPilot: {link}" if link else "",
                          "", "You receive this because email alerts are on for your account (Notifications > Alert rules)."])
        if _ses is None:
            _ses = boto3.client("ses")
        _ses.send_email(Source=ALERT_EMAIL_FROM, Destination={"ToAddresses": to},
                        Message={"Subject": {"Data": subject[:150]}, "Body": {"Text": {"Data": body}}})
        print(json.dumps({"email_sent": len(alerts), "account": aid, "to": len(to)}))
        return 1
    except Exception as e:
        print(json.dumps({"email_error": str(e), "account": aid}))
        return 0


def list_alerts(account_id, limit=50):
    from boto3.dynamodb.conditions import Key
    rows = TABLE.query(KeyConditionExpression=Key("PK").eq(f"ACCOUNT#{account_id}") & Key("SK").begins_with("ALERT#"),
                       ScanIndexForward=False, Limit=limit)["Items"]
    return [{"id": r["id"], "vehicle_id": r["vehicle_id"], "vehicle_name": r.get("vehicle_name"), **json.loads(r["alert"])} for r in rows]


def get_alert_settings(account_id):
    it = TABLE.get_item(Key={"PK": f"ACCOUNT#{account_id}", "SK": "ALERTSETTINGS"}).get("Item")
    return merged_settings(json.loads(it["settings"]) if it else {})


EMAIL_RE = __import__("re").compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_alert_settings(body):
    """Whitelist + range-check what the app may save. Raises ValueError with a readable message."""
    s = merged_settings({})
    if not isinstance(body, dict):
        raise ValueError("settings must be an object")
    if "enabled" in body:
        s["enabled"] = bool(body["enabled"])
    def num(k, lo, hi):
        if k in body:
            x = body[k]
            if not isinstance(x, (int, float)) or not lo <= x <= hi:
                raise ValueError(f"{k} must be between {lo} and {hi}")
            s[k] = int(x)
    num("offline_minutes", 30, 2880)
    num("speed_limit_kmh", 0, 250)
    num("low_battery_pct", 0, 100)
    ah = body.get("after_hours")
    if ah is not None:
        import re
        if not isinstance(ah, dict):
            raise ValueError("after_hours must be an object")
        for k in ("start", "end"):
            if k in ah and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", str(ah[k])):
                raise ValueError(f"after_hours.{k} must be HH:MM")
        days = ah.get("days", s["after_hours"]["days"])
        if not isinstance(days, list) or not all(isinstance(d, int) and 0 <= d <= 6 for d in days):
            raise ValueError("after_hours.days must be weekday numbers 0-6 (Mon=0)")
        s["after_hours"] = {**s["after_hours"], **{k: ah[k] for k in ("enabled", "start", "end") if k in ah}, "days": days}
        s["after_hours"]["enabled"] = bool(s["after_hours"]["enabled"])
    fences = body.get("geofences")
    if fences is not None:
        if not isinstance(fences, list) or len(fences) > 50:
            raise ValueError("geofences must be a list of at most 50")
        out = []
        for g in fences:
            try:
                f = {"id": str(g["id"])[:40], "name": str(g["name"])[:80], "lat": float(g["lat"]), "lon": float(g["lon"]),
                     "radius_m": float(g["radius_m"]), "on_enter": bool(g.get("on_enter", True)), "on_exit": bool(g.get("on_exit", True))}
            except (KeyError, TypeError, ValueError):
                raise ValueError("each geofence needs id, name, lat, lon, radius_m")
            if not (-90 <= f["lat"] <= 90 and -180 <= f["lon"] <= 180 and 50 <= f["radius_m"] <= 50000):
                raise ValueError(f"geofence {f['name']}: bad position or radius (50 m - 50 km)")
            out.append(f)
        s["geofences"] = out
    em = body.get("email")
    if em is not None:
        to = em.get("to", []) if isinstance(em, dict) else None
        if not isinstance(to, list) or len(to) > 5 or not all(isinstance(x, str) and EMAIL_RE.match(x) for x in to):
            raise ValueError("email.to must be up to 5 email addresses")
        s["email"] = {"enabled": bool(em.get("enabled", False)), "to": to}
    return s


WATCH_FOR_S = 45          # the edge server keeps pushing this long after the last poll
WATCH_REFRESH_S = 15      # re-write the flag at most this often per device (warm-container cache)
LIVE_MAX_AGE_S = 12       # a live position older than this is treated as "not moving any more"
_watch_written = {}


def live_positions(account_id, now=None):
    """GET /live: the account's latest *moving* positions (written by the edge server only while
    someone is watching) and, as a side effect, the 'someone is watching' flag the edge server reads."""
    from boto3.dynamodb.conditions import Key
    now = now if now is not None else time.time()
    rows = TABLE.query(KeyConditionExpression=Key("PK").eq(f"ACCOUNT#{account_id}") & Key("SK").begins_with("VEHICLE#"))["Items"]
    out = []
    for v in rows:
        dev = v["device_id"]
        if now - _watch_written.get(dev, 0) >= WATCH_REFRESH_S:
            TABLE.put_item(Item={"PK": f"DEVICE#{dev}", "SK": "WATCH", "watch_until": int(now) + WATCH_FOR_S, "ttl": int(now) + 3600})
            _watch_written[dev] = now
        live = TABLE.get_item(Key={"PK": f"DEVICE#{dev}", "SK": "LIVE"}).get("Item")
        age = (now - float(live["updated"])) if live else None
        fresh = live is not None and age <= LIVE_MAX_AGE_S
        out.append({
            "vehicle_id": v["SK"][8:], "device_id": dev,
            "live": {"lat": float(live["lat"]), "lon": float(live["lon"]), "speed_kmh": float(live["speed_kmh"]),
                     "course": int(live["course"]), "acc_on": bool(live["acc_on"]), "fix_time": live["fix_time"], "age_s": round(age, 1)} if fresh else None,
        })
    return {"now": int(now), "vehicles": out}


def _resp(code, body):
    return {"statusCode": code, "headers": {"Content-Type": "application/json", "Cache-Control": "no-store"},
            "body": json.dumps(body, default=str)}


def api(event, context):
    claims = event.get("requestContext", {}).get("authorizer", {}).get("jwt", {}).get("claims", {})
    sub = claims.get("sub")
    if not sub:
        return _resp(401, {"error": "not signed in"})
    user = TABLE.get_item(Key={"PK": f"USER#{sub}", "SK": "META"}).get("Item")
    if not user:
        return _resp(403, {"error": "no account linked to this login"})
    route = event.get("routeKey", "")
    if route == "GET /live" or (not route and event.get("rawPath", "").endswith("/live")):
        return _resp(200, live_positions(user["account_id"]))
    if route == "GET /alerts":
        return _resp(200, {"alerts": list_alerts(user["account_id"])})
    if route == "GET /alert-settings":
        return _resp(200, get_alert_settings(user["account_id"]))
    if route == "PUT /alert-settings":
        if user.get("role", "owner") not in ("owner", "manager"):
            return _resp(403, {"error": "only owners and managers can change alert settings"})
        try:
            s = validate_alert_settings(json.loads(event.get("body") or "{}"))
        except (ValueError, json.JSONDecodeError) as e:
            return _resp(400, {"error": str(e)})
        TABLE.put_item(Item={"PK": f"ACCOUNT#{user['account_id']}", "SK": "ALERTSETTINGS", "settings": json.dumps(s)})
        return _resp(200, s)
    body = _get_json(f"gold/accounts/{user['account_id']}/latest.json", None)
    if body is None:
        return _resp(404, {"error": "no data yet"})
    return _resp(200, body)
