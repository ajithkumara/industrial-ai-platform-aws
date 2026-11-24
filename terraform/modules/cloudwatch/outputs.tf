output "log_group_name"   { value = aws_cloudwatch_log_group.consumer.name }
output "alarm_topic_arn"  { value = aws_sns_topic.alarms.arn }
output "dashboard_name"   { value = aws_cloudwatch_dashboard.pipeline.dashboard_name }
output "dashboard_url"    { value = "https://ca-central-1.console.aws.amazon.com/cloudwatch/home?region=ca-central-1#dashboards:name=${aws_cloudwatch_dashboard.pipeline.dashboard_name}" }
