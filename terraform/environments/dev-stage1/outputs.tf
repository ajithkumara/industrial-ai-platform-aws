output "s3_bucket" {
  description = "S3 lake bucket name. Set S3_BUCKET=<this> when running the consumer."
  value       = aws_s3_bucket.lake.id
}

output "kinesis_stream_name" {
  description = "Kinesis stream name. Set KINESIS_STREAM_NAME=<this>."
  value       = one(aws_kinesis_stream.telemetry[*].name)
}

output "kinesis_stream_arn" {
  value = one(aws_kinesis_stream.telemetry[*].arn)
}

output "dynamodb_checkpoint_table" {
  description = "DynamoDB checkpoint table name. Set DYNAMODB_TABLE=<this>."
  value       = aws_dynamodb_table.checkpoints.name
}

output "consumer_role_arn" {
  description = "IAM role for the consumer process."
  value       = aws_iam_role.consumer.arn
}

output "producer_role_arn" {
  description = "IAM role for the producer process."
  value       = aws_iam_role.producer.arn
}

output "github_ci_role_arn" {
  description = "GitHub OIDC CI role ARN (empty when github_org is not set)."
  value       = length(aws_iam_role.github_ci) > 0 ? aws_iam_role.github_ci[0].arn : ""
}

output "aws_region" {
  value = data.aws_region.current.name
}

output "cost_reminder" {
  description = "Cost reminder."
  value       = "REMINDER: edge server (t4g.nano + public IPv4) ~ $8/month running, ~ $4.50/month stopped (IPv4 + EBS). Stop instance when not testing: aws ec2 stop-instances --instance-ids $(terraform output -raw edge_server_instance_id)"
}

output "cloudwatch_dashboard_url" {
  description = "CloudWatch pipeline dashboard URL."
  value       = one(module.monitoring[*].dashboard_url)
}

output "alarm_topic_arn" {
  description = "SNS topic ARN for pipeline alarms."
  value       = one(module.monitoring[*].alarm_topic_arn)
}

output "log_group_name" {
  description = "CloudWatch log group for the consumer."
  value       = one(module.monitoring[*].log_group_name)
}

# ── Athena ──────────────────────────────────────────────────────────────────
output "athena_database" {
  description = "Glue catalog database name."
  value       = module.athena.database_name
}

output "athena_workgroup" {
  description = "Athena workgroup name."
  value       = module.athena.workgroup_name
}

output "athena_results_bucket" {
  description = "S3 bucket for Athena query results."
  value       = module.athena.results_bucket
}

# ── Fleet API ────────────────────────────────────────────────────────────────
output "fleet_api_url" {
  description = "Base URL for the Fleet API (paste into dashboard)."
  value       = module.fleet_api.api_url
}

output "fleet_api_data_endpoint" {
  description = "GET /data — returns cached fleet data."
  value       = module.fleet_api.data_endpoint
}

output "fleet_api_refresh_endpoint" {
  description = "GET /refresh — triggers Athena rebuild (10-30s)."
  value       = module.fleet_api.refresh_endpoint
}

output "fleet_lambda_name" {
  description = "Lambda function name for the fleet API."
  value       = module.fleet_api.lambda_function_name
}

# ── Edge Server ───────────────────────────────────────────────────────────────

output "edge_server_public_ip" {
  description = "Elastic IP — enter this as Server in Mictrack Config Tool (Port 5013)"
  value       = module.edge_server.public_ip
}

output "edge_tcp_endpoint" {
  description = "Full TCP endpoint for device config: <IP>:5013"
  value       = module.edge_server.tcp_endpoint
}

output "edge_server_instance_id" {
  description = "EC2 instance ID (use to stop/start without destroying)"
  value       = module.edge_server.instance_id
}

# ── MP91 tracking dashboard ─────────────────────────────────────────────────
output "tracking_dashboard_url" {
  value = module.mp91_tracking.dashboard_url
}

output "tracking_api_url" {
  value = module.mp91_tracking.api_url
}

output "tracking_fleet_table" {
  description = "Fleet DynamoDB table (the edge server writes live positions to it; set as FLEET_TABLE in /opt/iap-edge/.env)"
  value       = module.mp91_tracking.fleet_table
}

output "tracking_dns_records_for_ionos" {
  value = module.mp91_tracking.dns_records_for_ionos
}

output "tracking_email_dns_records_for_ionos" {
  value = module.mp91_tracking.email_dns_records_for_ionos
}
