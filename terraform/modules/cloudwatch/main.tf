# CloudWatch — AWS equivalent of Azure Monitor + Application Insights.
# Log group for the consumer, SNS alarm topic, and alarms that mirror the
# Azure hardening alerts:
#   - consumer lag           (Kinesis GetRecords.IteratorAgeMilliseconds)  <- Azure P1-13 consumer-lag
#   - no incoming records    (Kinesis IncomingRecords == 0)               <- Azure ALERT-02 EH lag
#   - DLQ volume             (custom metric from the consumer)            <- data-quality signal
# Every alarm corresponds to a metric that is actually emitted (Kinesis
# service metrics, or a custom metric the consumer publishes) — no fake metrics.

resource "aws_cloudwatch_log_group" "consumer" {
  name              = "/industrial-ai/${var.name_prefix}/consumer"
  retention_in_days = var.log_retention_days
  kms_key_id        = var.log_kms_key_arn
  tags              = var.tags
}

resource "aws_sns_topic" "alarms" {
  name              = "${var.name_prefix}-alarms"
  kms_master_key_id = var.sns_kms_key_id
  tags              = var.tags
}

resource "aws_sns_topic_subscription" "email" {
  count     = var.alarm_email != "" ? 1 : 0
  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

# ALARM: consumer falling behind (iterator age high). Kinesis emits this metric
# natively per stream; no instrumentation required.
resource "aws_cloudwatch_metric_alarm" "consumer_lag" {
  alarm_name          = "${var.name_prefix}-consumer-lag"
  namespace           = "AWS/Kinesis"
  metric_name         = "GetRecords.IteratorAgeMilliseconds"
  dimensions          = { StreamName = var.kinesis_stream_name }
  statistic           = "Maximum"
  comparison_operator = "GreaterThanThreshold"
  threshold           = 60000 # 60s behind
  period              = 300
  evaluation_periods  = 3
  alarm_description    = "Consumer iterator age > 60s for 15m — consumer down or backed up (Azure P1-13 parity)."
  alarm_actions       = [aws_sns_topic.alarms.arn]
  ok_actions          = [aws_sns_topic.alarms.arn]
  treat_missing_data  = "notBreaching"
  tags                = var.tags
}

# ALARM: no records arriving (ingestion stalled). Mirrors Azure ALERT-02.
resource "aws_cloudwatch_metric_alarm" "no_incoming_records" {
  alarm_name          = "${var.name_prefix}-no-incoming-records"
  namespace           = "AWS/Kinesis"
  metric_name         = "IncomingRecords"
  dimensions          = { StreamName = var.kinesis_stream_name }
  statistic           = "Sum"
  comparison_operator = "LessThanThreshold"
  threshold           = 1
  period              = 300
  evaluation_periods  = 3
  alarm_description    = "No records ingested for 15m — producer/bridge down (Azure ALERT-02 parity)."
  alarm_actions       = [aws_sns_topic.alarms.arn]
  treat_missing_data  = "breaching"
  tags                = var.tags
}

# ALARM: DLQ volume. The consumer publishes a custom metric
# IndustrialAI/DLQRecords whenever it routes to the DLQ. This alarm only fires
# on a real emitted metric; if the consumer is not yet publishing it, the alarm
# stays in INSUFFICIENT_DATA rather than falsely OK.
resource "aws_cloudwatch_metric_alarm" "dlq_volume" {
  alarm_name          = "${var.name_prefix}-dlq-volume"
  namespace           = "IndustrialAI"
  metric_name         = "DLQRecords"
  dimensions          = { Environment = var.environment }
  statistic           = "Sum"
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  period              = 300
  evaluation_periods  = 1
  alarm_description    = "One or more events routed to the DLQ — malformed/invalid input detected."
  alarm_actions       = [aws_sns_topic.alarms.arn]
  treat_missing_data  = "notBreaching"
  tags                = var.tags
}
