"""
Upload generated telemetry JSONL files to S3 lake bucket.
Preserves Hive partition structure: year=/month=/day=/
Usage:
  $env:AWS_PROFILE = "iap-dev"
  $env:S3_BUCKET   = "iap-dev-lake-313092058964"
  python scripts/upload_to_s3.py

  # Optional: override data directory (default: sibling repo's data folder)
  $env:DATA_DIR = "C:\\path\\to\\data\\raw\\telemetry"
  python scripts/upload_to_s3.py
"""

import os
import sys
from pathlib import Path

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
except ImportError:
    print("ERROR: boto3 not installed. Run: pip install boto3")
    sys.exit(1)

BUCKET = os.environ.get("S3_BUCKET", "iap-dev-lake-313092058964")
REGION = os.environ.get("AWS_REGION", "ca-central-1")
PREFIX = "raw/telemetry"

def upload_folder(local_base: Path, bucket: str):
    s3 = boto3.client("s3", region_name=REGION)

    # Verify bucket access
    try:
        s3.head_bucket(Bucket=bucket)
        print(f"Bucket: s3://{bucket}/{PREFIX}")
    except ClientError as e:
        print(f"ERROR: Cannot access bucket '{bucket}': {e}")
        sys.exit(1)
    except NoCredentialsError:
        print("ERROR: AWS credentials not found. Set $env:AWS_PROFILE or configure ~/.aws/credentials")
        sys.exit(1)

    files = list(local_base.rglob("*.jsonl"))
    if not files:
        print(f"No .jsonl files found under {local_base}")
        sys.exit(1)

    print(f"Uploading {len(files)} file(s)...")
    total_bytes = 0
    for f in sorted(files):
        rel = f.relative_to(local_base)           # e.g. year=2026/month=09/day=10/telemetry.jsonl
        key = f"{PREFIX}/{rel}".replace("\\", "/")
        size = f.stat().st_size
        total_bytes += size
        print(f"  {rel}  ({size/1024:.1f} KB) → s3://{bucket}/{key}")
        s3.upload_file(
            str(f), bucket, key,
            ExtraArgs={"ContentType": "application/x-ndjson",
                       "ServerSideEncryption": "AES256"}
        )

    print(f"\nUpload complete: {len(files)} files, {total_bytes/1024/1024:.1f} MB total")
    print(f"Browse at: https://s3.console.aws.amazon.com/s3/buckets/{bucket}?prefix={PREFIX}/")

if __name__ == "__main__":
    # DATA_DIR env var → explicit path
    # Otherwise: look in sibling industrial-ai-platform repo (same parent folder)
    if os.environ.get("DATA_DIR"):
        base = Path(os.environ["DATA_DIR"])
    else:
        this_repo = Path(__file__).parent.parent          # industrial-ai-platform-aws/
        sibling   = this_repo.parent / "industrial-ai-platform" / "data" / "raw" / "telemetry"
        own       = this_repo / "data" / "raw" / "telemetry"
        base      = sibling if sibling.exists() else own

    if not base.exists():
        print(f"ERROR: Data folder not found: {base}")
        print("Options:")
        print("  1. Run: python scripts/generate_sample_data.py  (in industrial-ai-platform)")
        print("  2. Set: $env:DATA_DIR = 'C:\\path\\to\\data\\raw\\telemetry'")
        sys.exit(1)

    print(f"Source: {base}")
    upload_folder(base, BUCKET)
