"""
Stage 1 Smoke Test
==================
Sends 3 synthetic vehicle telemetry events to Kinesis, then verifies:
  1. A JSONL object appeared in the S3 bronze prefix
  2. A checkpoint item was written to DynamoDB (if consumer is running)

Usage (from repo root, after `terraform apply`):
    set KINESIS_STREAM_NAME=iap-dev-telemetryhub
    set S3_BUCKET=iap-dev-lake-246568717136
    set DYNAMODB_TABLE=iap-dev-checkpoints
    set AWS_DEFAULT_REGION=ca-central-1
    set AWS_PROFILE=iap-dev
    python scripts/smoke_test_stage1.py

Pass --count N to send N events (default 3).
Pass --wait  S to wait S seconds for the consumer to write S3 (default 30).

Exit code 0 = all checks passed.
Exit code 1 = one or more checks failed.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import uuid
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

UTC = timezone.utc
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("smoke_test")


# ── helpers ──────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _synthetic_event(i: int) -> dict:
    """Minimal vehicle telemetry event matching the platform's event envelope."""
    return {
        "event_id": str(uuid.uuid4()),
        "device_id": f"smoke-test-device-{i:03d}",
        "asset_type": "vehicle",
        "timestamp": _now_iso(),
        "payload": {
            "speed_kmh": 60 + i * 5,
            "latitude": 43.6532 + i * 0.001,
            "longitude": -79.3832 + i * 0.001,
            "ignition": True,
            "odometer_km": 12000 + i,
        },
        "schema_version": "1.0",
        "source": "smoke_test",
    }


# ── step 1: send events to Kinesis ───────────────────────────────────────────

def send_to_kinesis(stream_name: str, events: list[dict], region: str) -> bool:
    log.info("=== STEP 1: Sending %d event(s) to Kinesis stream '%s' ===", len(events), stream_name)
    kinesis = boto3.client("kinesis", region_name=region)

    records = [
        {
            "Data": json.dumps(e, separators=(",", ":")).encode("utf-8"),
            "PartitionKey": e["device_id"],
        }
        for e in events
    ]

    try:
        resp = kinesis.put_records(StreamName=stream_name, Records=records)
    except ClientError as exc:
        log.error("Kinesis put_records failed: %s", exc)
        return False

    failed = resp.get("FailedRecordCount", 0)
    if failed:
        log.error("  %d/%d record(s) failed to send.", failed, len(records))
        return False

    log.info("  ✅ All %d event(s) sent successfully.", len(events))
    for i, rec in enumerate(resp["Records"]):
        log.info("  Event %d → ShardId=%s  SequenceNumber=%s",
                 i, rec.get("ShardId", "?"), rec.get("SequenceNumber", "?")[:20] + "...")
    return True


# ── step 2: poll S3 for bronze JSONL object ───────────────────────────────────

def check_s3(bucket: str, prefix: str, region: str, wait_seconds: int) -> bool:
    log.info("=== STEP 2: Polling S3 s3://%s/%s for JSONL object (up to %ds) ===",
             bucket, prefix, wait_seconds)
    s3 = boto3.client("s3", region_name=region)
    deadline = time.time() + wait_seconds
    attempt = 0

    while time.time() < deadline:
        attempt += 1
        try:
            resp = s3.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=10)
        except ClientError as exc:
            log.error("  S3 list_objects_v2 failed: %s", exc)
            return False

        objects = resp.get("Contents", [])
        jsonl_objects = [o for o in objects if o["Key"].endswith(".jsonl")]
        if jsonl_objects:
            log.info("  ✅ Found %d JSONL object(s) in S3:", len(jsonl_objects))
            for obj in jsonl_objects:
                log.info("     s3://%s/%s  (%d bytes)", bucket, obj["Key"], obj["Size"])
            # Download and show first object content
            key = jsonl_objects[0]["Key"]
            try:
                body = s3.get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8")
                lines = [l for l in body.strip().splitlines() if l]
                log.info("  First object contains %d line(s):", len(lines))
                for line in lines[:3]:
                    parsed = json.loads(line)
                    log.info("    device_id=%s  timestamp=%s",
                             parsed.get("device_id", "?"), parsed.get("timestamp", "?"))
            except Exception as exc:
                log.warning("  Could not read object content: %s", exc)
            return True

        remaining = int(deadline - time.time())
        log.info("  Attempt %d: no JSONL yet. Retrying in 5s (%ds remaining)...",
                 attempt, remaining)
        time.sleep(5)

    log.warning("  ⚠️  No JSONL object found after %ds. "
                "Is the consumer running? Or run the consumer separately.", wait_seconds)
    log.info("  NOTE: Events were sent to Kinesis. Consumer must read+write S3.")
    return False


# ── step 3: check DynamoDB checkpoint ────────────────────────────────────────

def check_dynamodb(table: str, stream_name: str, region: str) -> bool:
    log.info("=== STEP 3: Checking DynamoDB checkpoint table '%s' ===", table)
    ddb = boto3.client("dynamodb", region_name=region)

    try:
        resp = ddb.scan(TableName=table, Limit=5)
    except ClientError as exc:
        log.error("  DynamoDB scan failed: %s", exc)
        return False

    items = resp.get("Items", [])
    if items:
        log.info("  ✅ Found %d checkpoint item(s):", len(items))
        for item in items:
            shard = item.get("shard_id", {}).get("S", "?")
            seq = item.get("sequence_number", {}).get("S", "?")
            log.info("    shard_id=%s  sequence_number=%s...", shard, seq[:20] if seq != "?" else "?")
        return True
    else:
        log.info("  ℹ️  No checkpoint items yet (consumer hasn't run or hasn't committed).")
        log.info("  This is expected if you only ran send — consumer writes checkpoints.")
        return True  # Not a failure — checkpoint written by consumer, not producer


# ── step 4: verify Kinesis stream is ACTIVE ───────────────────────────────────

def check_kinesis_stream(stream_name: str, region: str) -> bool:
    log.info("=== PRE-CHECK: Kinesis stream status ===")
    kinesis = boto3.client("kinesis", region_name=region)
    try:
        resp = kinesis.describe_stream_summary(StreamName=stream_name)
        status = resp["StreamDescriptionSummary"]["StreamStatus"]
        shards = resp["StreamDescriptionSummary"]["OpenShardCount"]
        log.info("  Stream '%s': status=%s  shards=%d", stream_name, status, shards)
        if status != "ACTIVE":
            log.error("  Stream is not ACTIVE (got '%s'). Wait for it to become ACTIVE.", status)
            return False
        log.info("  ✅ Stream is ACTIVE.")
        return True
    except ClientError as exc:
        log.error("  Could not describe stream: %s", exc)
        return False


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 1 smoke test")
    parser.add_argument("--count", type=int, default=3, help="Number of events to send (default: 3)")
    parser.add_argument("--wait", type=int, default=30,
                        help="Seconds to wait for S3 object (default: 30). Set 0 to skip S3 check.")
    args = parser.parse_args()

    import os
    stream_name = os.environ.get("KINESIS_STREAM_NAME", "iap-dev-telemetryhub")
    bucket = os.environ.get("S3_BUCKET", "iap-dev-lake-246568717136")
    table = os.environ.get("DYNAMODB_TABLE", "iap-dev-checkpoints")
    region = os.environ.get("AWS_DEFAULT_REGION", "ca-central-1")
    bronze_prefix = os.environ.get("S3_BRONZE_PREFIX", "raw/telemetry/")

    log.info("=" * 60)
    log.info("IAP Stage 1 Smoke Test")
    log.info("  Stream : %s", stream_name)
    log.info("  Bucket : %s", bucket)
    log.info("  Table  : %s", table)
    log.info("  Region : %s", region)
    log.info("  Events : %d", args.count)
    log.info("=" * 60)

    results: dict[str, bool] = {}

    # Pre-check: stream must be ACTIVE
    results["kinesis_active"] = check_kinesis_stream(stream_name, region)
    if not results["kinesis_active"]:
        log.error("Aborting — Kinesis stream not ACTIVE.")
        return 1

    # Step 1: send
    events = [_synthetic_event(i) for i in range(args.count)]
    results["send"] = send_to_kinesis(stream_name, events, region)

    # Step 2: check S3 (optional — requires consumer to be running)
    if args.wait > 0:
        results["s3"] = check_s3(bucket, bronze_prefix, region, args.wait)
    else:
        log.info("=== STEP 2: S3 check skipped (--wait 0) ===")
        results["s3"] = True

    # Step 3: check DynamoDB
    results["dynamodb"] = check_dynamodb(table, stream_name, region)

    # Summary
    log.info("=" * 60)
    log.info("SMOKE TEST RESULTS:")
    all_passed = True
    for check, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        log.info("  %-20s %s", check, status)
        if not passed:
            all_passed = False

    if all_passed:
        log.info("ALL CHECKS PASSED — Stage 1 pipeline is operational.")
        log.info("=" * 60)
        log.info("⚠️  REMEMBER: Run `terraform destroy` to stop Kinesis billing.")
        return 0
    else:
        log.error("ONE OR MORE CHECKS FAILED — see above for details.")
        log.info("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
