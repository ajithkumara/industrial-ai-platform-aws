# Kinesis Data Stream — AWS equivalent of Azure Event Hubs. 168h (7-day)
# retention mirrors the Azure P1-14 change. KMS encryption at rest.

resource "aws_kinesis_stream" "this" {
  name             = "${var.name_prefix}-telemetry"
  shard_count      = var.shard_count
  retention_period = var.retention_hours # 168 = 7 days (Azure P1-14 parity)

  encryption_type = "KMS"
  kms_key_id      = var.kms_key_arn

  stream_mode_details {
    stream_mode = "PROVISIONED"
  }

  tags = var.tags
}
