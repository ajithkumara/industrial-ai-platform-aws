"""Multi-tenant isolation for the MP91 Lambda (moto). A login only ever sees its own account."""
import importlib
import json
import os
import sys

import boto3
import pytest
from moto import mock_aws

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = bytes.fromhex("24701853201904515507112643266591060794052976000000fffffbff0003daa600000000012e00d6e7000004")


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("LAKE_BUCKET", "lake-test")
    monkeypatch.setenv("FLEET_TABLE", "fleet")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ca-central-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "x")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "x")
    sys.path[:0] = [os.path.join(ROOT, "lambda", "mp91_processor"), os.path.join(ROOT, "edge")]
    with mock_aws():
        boto3.client("s3").create_bucket(Bucket="lake-test", CreateBucketConfiguration={"LocationConstraint": "ca-central-1"})
        boto3.client("dynamodb").create_table(
            TableName="fleet", BillingMode="PAY_PER_REQUEST",
            KeySchema=[{"AttributeName": "PK", "KeyType": "HASH"}, {"AttributeName": "SK", "KeyType": "RANGE"}],
            AttributeDefinitions=[{"AttributeName": "PK", "AttributeType": "S"}, {"AttributeName": "SK", "AttributeType": "S"}])
        t = boto3.resource("dynamodb").Table("fleet")
        for it in [
            {"PK": "ACCOUNT#ajith", "SK": "META", "name": "Ajith", "kind": "personal"},
            {"PK": "ACCOUNT#ajith", "SK": "VEHICLE#car1", "name": "My car", "device_id": "7018532019"},
            {"PK": "USER#sub-1", "SK": "META", "account_id": "ajith"},
            {"PK": "ACCOUNT#acme", "SK": "META", "name": "Acme HVAC", "kind": "fleet"},
            {"PK": "ACCOUNT#acme", "SK": "VEHICLE#van1", "name": "Van 1", "device_id": "999"},
            {"PK": "USER#sub-2", "SK": "META", "account_id": "acme"},
        ]:
            t.put_item(Item=it)
        import handler
        yield importlib.reload(handler)
        sys.path[:2] = []


def _ev(sub):
    return {"requestContext": {"authorizer": {"jwt": {"claims": {"sub": sub}}}}}


def test_each_login_sees_only_its_own_account(env):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    line = json.dumps({"event_id": "e1", "raw_hex": BIN.hex()})
    boto3.client("s3").put_object(Bucket="lake-test", Key=f"raw/mp91/year={now:%Y}/month={now:%m}/day={now:%d}/f.jsonl", Body=line.encode())
    assert env.process({}, None)["accounts"] == 2
    a = json.loads(env.api(_ev("sub-1"), None)["body"])
    b = json.loads(env.api(_ev("sub-2"), None)["body"])
    assert a["account_id"] == "ajith" and a["vehicles"][0]["current"] is not None
    assert b["account_id"] == "acme" and b["vehicles"][0]["current"] is None   # never sees Ajith's device
    assert env.api(_ev("unknown"), None)["statusCode"] == 403
    assert env.api({}, None)["statusCode"] == 401


def test_live_endpoint_is_scoped_flags_watch_and_hides_stale(env):
    import time
    t = boto3.resource("dynamodb").Table("fleet")
    now = time.time()
    t.put_item(Item={"PK": "DEVICE#7018532019", "SK": "LIVE", "lat": "43.44", "lon": "-79.67", "speed_kmh": "41.5", "course": 90,
                     "acc_on": True, "fix_time": "2026-11-14T22:00:01+00:00", "updated": int(now) - 2})
    t.put_item(Item={"PK": "DEVICE#999", "SK": "LIVE", "lat": "1", "lon": "2", "speed_kmh": "50", "course": 0,
                     "acc_on": True, "fix_time": "x", "updated": int(now) - 1})
    a = env.api({**_ev("sub-1"), "routeKey": "GET /live"}, None)
    body = json.loads(a["body"])
    assert a["statusCode"] == 200
    assert [v["device_id"] for v in body["vehicles"]] == ["7018532019"]          # never sees acme's device 999
    assert body["vehicles"][0]["live"]["speed_kmh"] == 41.5
    watch = t.get_item(Key={"PK": "DEVICE#7018532019", "SK": "WATCH"})["Item"]   # edge server will see this flag
    assert int(watch["watch_until"]) > now + 30
    assert t.get_item(Key={"PK": "DEVICE#999", "SK": "WATCH"}).get("Item") is None
    t.put_item(Item={"PK": "DEVICE#7018532019", "SK": "LIVE", "lat": "43.44", "lon": "-79.67", "speed_kmh": "41.5", "course": 90,
                     "acc_on": True, "fix_time": "x", "updated": int(now) - 60})
    body = json.loads(env.api({**_ev("sub-1"), "routeKey": "GET /live"}, None)["body"])
    assert body["vehicles"][0]["live"] is None                                    # stale = not moving any more


def test_gold_never_contains_another_accounts_device(env):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    line = json.dumps({"event_id": "e1", "raw_hex": BIN.hex()})
    boto3.client("s3").put_object(Bucket="lake-test", Key=f"raw/mp91/year={now:%Y}/month={now:%m}/day={now:%d}/f.jsonl", Body=line.encode())
    env.process({}, None)
    a = json.loads(env.api(_ev("sub-1"), None)["body"])
    b_raw = env.api(_ev("sub-2"), None)["body"]
    assert "7018532019" not in b_raw and "My car" not in b_raw          # nothing of Ajith's anywhere in Acme's payload
    assert a["vehicles"][0]["device"]["messages"] >= 1                  # device health block present for the owner
    assert json.loads(b_raw)["vehicles"][0]["device"] is None           # Acme's device has sent nothing


def test_request_parameters_cannot_select_another_account(env):
    """The account always comes from the verified login (USER#<sub>), never from the request."""
    ev = _ev("sub-1")
    ev.update(queryStringParameters={"account_id": "acme"}, pathParameters={"account": "acme"}, rawPath="/mp91", body=json.dumps({"account_id": "acme"}))
    env.process({"force": True}, None)
    body = json.loads(env.api(ev, None)["body"])
    assert body["account_id"] == "ajith"
    live = json.loads(env.api({**_ev("sub-2"), "routeKey": "GET /live", "queryStringParameters": {"account_id": "ajith"}}, None)["body"])
    assert [v["device_id"] for v in live["vehicles"]] == ["999"]


def test_late_raw_files_from_older_days_are_swept(env):
    from datetime import datetime, timedelta, timezone
    old = datetime.now(timezone.utc) - timedelta(days=4)
    line = json.dumps({"event_id": "e1", "raw_hex": BIN.hex()})
    boto3.client("s3").put_object(Bucket="lake-test", Key=f"raw/mp91/year={old:%Y}/month={old:%m}/day={old:%d}/late.jsonl", Body=line.encode())
    env.process({"backlog": True}, None)                               # the hourly sweep does
    silver = json.loads(boto3.client("s3").get_object(Bucket="lake-test", Key=f"silver/mp91/days/{old:%Y-%m-%d}.json")["Body"].read())
    assert any(k.endswith("late.jsonl") for k in silver["processed"])


def test_backlog_window_is_hourly_only(env):
    from datetime import datetime, timezone
    assert len(env._days_to_scan(datetime(2026, 11, 24, 10, 30, 5, tzinfo=timezone.utc), {})) == 2
    assert len(env._days_to_scan(datetime(2026, 11, 24, 11, 0, 3, tzinfo=timezone.utc), {})) == env.BACKLOG_DAYS


def _put_raw(text_frame):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    line = json.dumps({"event_id": "e", "raw_hex": text_frame.encode().hex()})
    boto3.client("s3").put_object(Bucket="lake-test", Key=f"raw/mp91/year={now:%Y}/month={now:%m}/day={now:%d}/{now:%H%M%S%f}.jsonl", Body=line.encode())


def _frame(speed_knots, acc=True, ago_s=0):
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc) - timedelta(seconds=ago_s)
    status = "FFFFFFFF" if acc else "FFFFFBFF"
    return f"*HQ,7018532019,V1,{now:%H%M%S},A,4326.6589,N,07940.5293,W,{speed_knots:.2f},000,{now:%d%m%y},{status},302,720,1,2#"


def test_alert_settings_round_trip_validation_and_isolation(env):
    put = lambda sub, body: env.api({**_ev(sub), "routeKey": "PUT /alert-settings", "body": json.dumps(body)}, None)
    get = lambda sub: json.loads(env.api({**_ev(sub), "routeKey": "GET /alert-settings"}, None)["body"])
    assert get("sub-1")["speed_limit_kmh"] == 110                                   # defaults
    assert put("sub-1", {"speed_limit_kmh": 90, "geofences": [{"id": "h", "name": "Home", "lat": 43.44, "lon": -79.67, "radius_m": 150}]})["statusCode"] == 200
    assert get("sub-1")["speed_limit_kmh"] == 90 and get("sub-1")["geofences"][0]["name"] == "Home"
    assert get("sub-2")["speed_limit_kmh"] == 110 and get("sub-2")["geofences"] == []   # Acme unaffected
    assert put("sub-1", {"speed_limit_kmh": 999})["statusCode"] == 400
    assert put("sub-1", {"after_hours": {"start": "25:00"}})["statusCode"] == 400
    assert put("sub-1", {"email": {"enabled": True, "to": ["not-an-email"]}})["statusCode"] == 400
    assert put("sub-1", {"geofences": [{"id": "x", "name": "x", "lat": 43, "lon": -79, "radius_m": 5}]})["statusCode"] == 400


def test_speeding_alert_is_stored_for_the_owner_only(env):
    env.api({**_ev("sub-1"), "routeKey": "PUT /alert-settings", "body": json.dumps({"speed_limit_kmh": 50})}, None)
    _put_raw(_frame(10, ago_s=5))              # ~19 km/h: establishes state, no alert
    env.process({}, None)
    _put_raw(_frame(60))                      # ~111 km/h
    env.process({}, None)
    a = json.loads(env.api({**_ev("sub-1"), "routeKey": "GET /alerts"}, None)["body"])["alerts"]
    b = json.loads(env.api({**_ev("sub-2"), "routeKey": "GET /alerts"}, None)["body"])["alerts"]
    assert [x["kind"] for x in a] == ["speeding"] and a[0]["vehicle_name"] == "My car"
    assert b == []
    env.process({"force": True}, None)        # reprocessing the same data does not repeat it
    assert len(json.loads(env.api({**_ev("sub-1"), "routeKey": "GET /alerts"}, None)["body"])["alerts"]) == 1


def test_offline_sweep_runs_without_new_data(env):
    from datetime import datetime, timedelta, timezone
    _put_raw(_frame(0, acc=False))
    env.process({}, None)
    t = boto3.resource("dynamodb").Table("fleet")
    gold = json.loads(boto3.client("s3").get_object(Bucket="lake-test", Key="gold/accounts/ajith/latest.json")["Body"].read())
    gold["vehicles"][0]["device"]["last_contact"] = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
    boto3.client("s3").put_object(Bucket="lake-test", Key="gold/accounts/ajith/latest.json", Body=json.dumps(gold).encode())
    assert env.sweep_device_alerts() == 1
    assert env.sweep_device_alerts() == 0     # once per episode
    kinds = [x["kind"] for x in json.loads(env.api({**_ev("sub-1"), "routeKey": "GET /alerts"}, None)["body"])["alerts"]]
    assert kinds == ["offline"]


def _email_env(env, monkeypatch):
    boto3.client("ses").verify_domain_identity(Domain="example.com")
    monkeypatch.setattr(env, "ALERT_EMAIL_FROM", "FleetPilot Alerts <alerts@example.com>")
    monkeypatch.setattr(env, "_ses", None)
    env.api({**_ev("sub-1"), "routeKey": "PUT /alert-settings", "body": json.dumps({"speed_limit_kmh": 50, "email": {"enabled": True, "to": ["owner@example.com"]}})}, None)


def _sent():
    return int(boto3.client("ses").get_send_quota()["SentLast24Hours"])


def test_alert_email_sent_once_per_pass(env, monkeypatch):
    _email_env(env, monkeypatch)
    _put_raw(_frame(10, ago_s=5)); env.process({}, None)
    before = _sent()
    _put_raw(_frame(60)); env.process({}, None)
    assert _sent() == before + 1
    env.process({"force": True}, None)                 # nothing new: no email
    assert _sent() == before + 1


def test_no_email_when_off_or_no_sender(env, monkeypatch):
    _email_env(env, monkeypatch)
    env.api({**_ev("sub-1"), "routeKey": "PUT /alert-settings", "body": json.dumps({"speed_limit_kmh": 50, "email": {"enabled": False, "to": ["owner@example.com"]}})}, None)
    al = [{"time": "2026-11-24T10:00:00+00:00", "vehicle_name": "My car", "title": "t", "message": "m"}]
    assert env.email_alerts("ajith", env.get_alert_settings("ajith"), al) == 0
    monkeypatch.setattr(env, "ALERT_EMAIL_FROM", "")
    assert env.email_alerts("ajith", {"email": {"enabled": True, "to": ["owner@example.com"]}}, al) == 0


def test_email_hourly_limit(env, monkeypatch):
    _email_env(env, monkeypatch)
    monkeypatch.setattr(env, "EMAIL_MAX_PER_HOUR", 2)
    st = {"email": {"enabled": True, "to": ["owner@example.com"]}}
    al = [{"time": "2026-11-24T10:00:00+00:00", "vehicle_name": "My car", "title": "t", "message": "m"}]
    assert [env.email_alerts("ajith", st, al) for _ in range(4)] == [1, 1, 0, 0]
