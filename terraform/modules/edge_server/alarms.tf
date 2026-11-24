##############################################################################
# Edge server self-healing (Phase 2)
#
#   system check failed  (AWS host/hardware/network problem) -> EC2 RECOVER
#       Moves the SAME instance to healthy hardware: same instance id, same
#       Elastic IP, same EBS disk (the listener's spool survives).
#   instance check failed (OS hung, out of memory, kernel issue) -> EC2 REBOOT
#
# Both alarms also notify the SNS topic; subscribe an email with var.alarm_email
# (AWS sends a confirmation email first — click the link once).
#
# COST: 2 standard alarms x ~$0.10/month; SNS email notifications free at this volume.
# EC2 status-check metrics are reported every minute at no charge.
# Adding these resources does NOT modify or replace the instance.
##############################################################################

resource "aws_sns_topic" "edge_alarms" {
  name = "${var.name_prefix}-edge-alarms"
  tags = var.tags
}

resource "aws_sns_topic_subscription" "edge_alarms_email" {
  count     = var.alarm_email != "" ? 1 : 0
  topic_arn = aws_sns_topic.edge_alarms.arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

resource "aws_cloudwatch_metric_alarm" "edge_system_check" {
  alarm_name          = "${var.name_prefix}-edge-system-check-recover"
  alarm_description   = "AWS-side failure on the MP91 edge server: recover the instance onto healthy hardware (same IP, same disk)."
  namespace           = "AWS/EC2"
  metric_name         = "StatusCheckFailed_System"
  dimensions          = { InstanceId = aws_instance.edge_server.id }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 2
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "missing"
  alarm_actions       = ["arn:aws:automate:${var.region}:ec2:recover", aws_sns_topic.edge_alarms.arn]
  ok_actions          = [aws_sns_topic.edge_alarms.arn]
  tags                = var.tags
}

resource "aws_cloudwatch_metric_alarm" "edge_instance_check" {
  alarm_name          = "${var.name_prefix}-edge-instance-check-reboot"
  alarm_description   = "MP91 edge server OS is unresponsive: reboot it. The listener restarts on boot and replays its disk spool."
  namespace           = "AWS/EC2"
  metric_name         = "StatusCheckFailed_Instance"
  dimensions          = { InstanceId = aws_instance.edge_server.id }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 3
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "missing"
  alarm_actions       = ["arn:aws:automate:${var.region}:ec2:reboot", aws_sns_topic.edge_alarms.arn]
  ok_actions          = [aws_sns_topic.edge_alarms.arn]
  tags                = var.tags
}
