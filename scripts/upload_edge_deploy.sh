#!/usr/bin/env bash
# Upload edge listener code to S3 deploy prefix.
# Run this AFTER terraform apply so the EC2 instance can download the real
# tcp_listener.py + s3_writer.py on next boot (or after: sudo systemctl restart iap-edge).
#
# Usage:
#   BUCKET=$(cd terraform/environments/dev-stage1 && terraform output -raw s3_bucket)
#   bash scripts/upload_edge_deploy.sh "$BUCKET"
#
# Or pass bucket name directly:
#   bash scripts/upload_edge_deploy.sh iap-dev-lake-abc123

set -euo pipefail

BUCKET="${1:?Usage: $0 <s3-bucket-name>}"
REGION="${AWS_DEFAULT_REGION:-ca-central-1}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "Uploading edge code to s3://$BUCKET/deploy/edge/ ..."

aws s3 cp "$REPO_ROOT/edge/tcp_listener.py" \
    "s3://$BUCKET/deploy/edge/tcp_listener.py" \
    --region "$REGION"

aws s3 cp "$REPO_ROOT/edge/s3_writer.py" \
    "s3://$BUCKET/deploy/edge/s3_writer.py" \
    --region "$REGION"

echo "Done. Files uploaded:"
aws s3 ls "s3://$BUCKET/deploy/edge/" --region "$REGION"

echo ""
echo "To apply on the running EC2 instance (if already running):"
echo "  INSTANCE_ID=\$(cd terraform/environments/dev-stage1 && terraform output -raw edge_server_instance_id)"
echo "  aws ssm send-command \\"
echo "    --instance-ids \"\$INSTANCE_ID\" \\"
echo "    --document-name 'AWS-RunShellScript' \\"
echo "    --parameters 'commands=[\"aws s3 cp s3://$BUCKET/deploy/edge/tcp_listener.py /opt/iap-edge/tcp_listener.py\",\"aws s3 cp s3://$BUCKET/deploy/edge/s3_writer.py /opt/iap-edge/s3_writer.py\",\"systemctl restart iap-edge\"]'"
