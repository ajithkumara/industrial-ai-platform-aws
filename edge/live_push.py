"""Hot path: push the car's latest position to DynamoDB, only while it is moving AND someone is watching.

stdlib only (the edge server has no pip packages): AWS Signature V4 is implemented by hand and the
instance-role credentials come from the metadata service (IMDSv2).

Items in the fleet table (single-table design, see lambda/mp91_processor/handler.py):
  PK DEVICE#<id>  SK WATCH   watch_until (epoch s)   written by the API while the Live Map is open
  PK DEVICE#<id>  SK LIVE    lat, lon, speed_kmh, course, acc_on, fix_time, updated, ttl   written here
S3 stays the complete system of record; this path only carries "where is the car right now".
"""
import hashlib
import hmac
import http.client
import json
import os
import threading
import time
from datetime import datetime, timezone

IMDS = "169.254.169.254"
MOVING_KMH = float(os.environ.get("LIVE_MOVING_KMH", "3.0"))
MAX_FIX_AGE_S = 60  # a fix older than this when it arrives is buffered history, never shown as live


def _age_s(fix_time, now=None):
    try:
        return (now or time.time()) - datetime.fromisoformat(fix_time).timestamp()
    except Exception:
        return float("inf")
MIN_INTERVAL = float(os.environ.get("LIVE_MIN_INTERVAL", "1.0"))   # max one write per device per second
WATCH_CACHE_S = float(os.environ.get("LIVE_WATCH_CACHE", "4.0"))   # how long a "watched?" answer is reused
LIVE_TTL_S = 24 * 3600


# ── credentials (IMDSv2) ──────────────────────────────────────────────────────

def _imds(method, path, headers=None):
    c = http.client.HTTPConnection(IMDS, timeout=2)
    try:
        c.request(method, path, headers=headers or {})
        r = c.getresponse()
        body = r.read().decode()
        if r.status != 200:
            raise RuntimeError(f"IMDS {path} -> {r.status}")
        return body
    finally:
        c.close()


class InstanceCreds:
    def __init__(self):
        self._c = None
        self._exp = 0.0
        self._lock = threading.Lock()

    def get(self):
        with self._lock:
            if self._c is None or time.time() > self._exp - 300:
                tok = _imds("PUT", "/latest/api/token", {"X-aws-ec2-metadata-token-ttl-seconds": "21600"})
                h = {"X-aws-ec2-metadata-token": tok}
                role = _imds("GET", "/latest/meta-data/iam/security-credentials/", h).split()[0]
                j = json.loads(_imds("GET", f"/latest/meta-data/iam/security-credentials/{role}", h))
                self._c = (j["AccessKeyId"], j["SecretAccessKey"], j["Token"])
                self._exp = datetime.strptime(j["Expiration"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
            return self._c


# ── SigV4 ─────────────────────────────────────────────────────────────────────

def _hmac(key, msg):
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def sign_v4(host, region, service, target, body, creds, amz_date):
    """Return the request headers (incl. Authorization) for a DynamoDB JSON POST to '/'."""
    access, secret, token = creds
    datestamp = amz_date[:8]
    payload_hash = hashlib.sha256(body).hexdigest()
    hdrs = {
        "content-type": "application/x-amz-json-1.0",
        "host": host,
        "x-amz-date": amz_date,
        "x-amz-security-token": token,
        "x-amz-target": target,
    }
    signed = ";".join(sorted(hdrs))
    canonical = "POST\n/\n\n" + "".join(f"{k}:{hdrs[k]}\n" for k in sorted(hdrs)) + "\n" + signed + "\n" + payload_hash
    scope = f"{datestamp}/{region}/{service}/aws4_request"
    to_sign = f"AWS4-HMAC-SHA256\n{amz_date}\n{scope}\n" + hashlib.sha256(canonical.encode()).hexdigest()
    k = _hmac(_hmac(_hmac(_hmac(("AWS4" + secret).encode(), datestamp), region), service), "aws4_request")
    sig = hmac.new(k, to_sign.encode(), hashlib.sha256).hexdigest()
    out = dict(hdrs)
    out["Authorization"] = f"AWS4-HMAC-SHA256 Credential={access}/{scope}, SignedHeaders={signed}, Signature={sig}"
    return out


class Dynamo:
    def __init__(self, table, region, creds=None):
        self.table, self.region = table, region
        self.host = f"dynamodb.{region}.amazonaws.com"
        self.creds = creds or InstanceCreds()

    def call(self, op, payload):
        body = json.dumps(payload, separators=(",", ":")).encode()
        amz_date = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        h = sign_v4(self.host, self.region, "dynamodb", f"DynamoDB_20120810.{op}", body, self.creds.get(), amz_date)
        c = http.client.HTTPSConnection(self.host, timeout=3)
        try:
            c.request("POST", "/", body=body, headers=h)
            r = c.getresponse()
            data = r.read()
            if r.status != 200:
                raise RuntimeError(f"DynamoDB {op} {r.status}: {data[:200]!r}")
            return json.loads(data)
        finally:
            c.close()

    def get(self, pk, sk):
        r = self.call("GetItem", {"TableName": self.table, "Key": {"PK": {"S": pk}, "SK": {"S": sk}}})
        return r.get("Item")

    def put(self, item):
        self.call("PutItem", {"TableName": self.table, "Item": item})


# ── publisher ─────────────────────────────────────────────────────────────────

def live_item(rec, now):
    return {
        "PK": {"S": f"DEVICE#{rec['device_id']}"}, "SK": {"S": "LIVE"},
        "lat": {"N": repr(float(rec["latitude"]))}, "lon": {"N": repr(float(rec["longitude"]))},
        "speed_kmh": {"N": repr(float(rec["speed_kmh"]))}, "course": {"N": str(int(rec.get("course_deg") or 0))},
        "acc_on": {"BOOL": bool(rec.get("acc_on"))}, "fix_time": {"S": rec["fix_time"]},
        "updated": {"N": str(int(now))}, "ttl": {"N": str(int(now) + LIVE_TTL_S)},
    }


class LivePublisher:
    """offer() is called from the socket thread and never blocks; a worker thread does the network I/O."""

    def __init__(self, table, region, log=print, db=None):
        self.db = db or Dynamo(table, region)
        self.log = log
        self._latest = {}      # device_id -> newest record not yet pushed
        self._last_put = {}    # device_id -> time of last write
        self._watch = {}       # device_id -> (checked_at, watched)
        self._lock = threading.Lock()
        self._wake = threading.Event()

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def offer(self, rec, now=None):
        if rec.get("gps_valid") is False or rec["speed_kmh"] <= MOVING_KMH:
            return  # parked / no fix: the slow S3 path covers it
        if rec.get("stored_data") or _age_s(rec["fix_time"], now) > MAX_FIX_AGE_S:
            return  # buffered / replayed after a coverage gap: history, not "live" (S3 path places it in its trip)
        with self._lock:
            cur = self._latest.get(rec["device_id"])
            if cur is None or rec["fix_time"] >= cur["fix_time"]:
                self._latest[rec["device_id"]] = rec
        self._wake.set()

    def watched(self, device_id, now=None):
        now = now or time.time()
        checked, val = self._watch.get(device_id, (0.0, False))
        if now - checked < WATCH_CACHE_S:
            return val
        item = self.db.get(f"DEVICE#{device_id}", "WATCH")
        val = bool(item) and float(item.get("watch_until", {}).get("N", "0")) > now
        self._watch[device_id] = (now, val)
        return val

    def flush_once(self, now=None):
        now = now or time.time()
        with self._lock:
            batch, self._latest = self._latest, {}
        for dev, rec in batch.items():
            if now - self._last_put.get(dev, 0.0) < MIN_INTERVAL:
                with self._lock:
                    self._latest.setdefault(dev, rec)   # try again next tick
                continue
            if not self.watched(dev, now):
                continue
            self.db.put(live_item(rec, now))
            self._last_put[dev] = now

    def _run(self):
        backoff = 0.0
        while True:
            self._wake.wait(timeout=1.0)
            self._wake.clear()
            time.sleep(backoff)
            try:
                self.flush_once()
                backoff = 0.0
            except Exception as e:  # never let the worker die; slow down while AWS is unreachable
                backoff = min(30.0, backoff * 2 or 1.0)
                self.log(f"live push error (retry in {backoff:.0f}s): {e}")
            time.sleep(max(0.0, MIN_INTERVAL / 2))
