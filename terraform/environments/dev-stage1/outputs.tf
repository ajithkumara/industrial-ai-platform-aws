output "s3_bucket" {
  description = "S3 lake bucket name. Set S3_BUCKET=<this> when running the consumer."
  value       = aws_s3_bucket.lake.id
}

output "kinesis_stream_name" {
  description = "Kinesis stream name. Set KINESIS_STREAM_NAME=<this>."
  value       = aws_kinesis_stream.telemetry.name
}

output "kinesis_stream_arn" {
  value = aws_kinesis_stream.telemetry.arn
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
  description = "Cost reminder — do not leave Kinesis running."
  value       = "REMINDER: Kinesis costs $0.015/shard-hr. Run `terraform destroy` after testing."
}

output "cloudwatch_dashboard_url" {
  description = "CloudWatch pipeline dashboard URL."
  value       = module.monitoring.dashboard_url
}

output "alarm_topic_arn" {
  description = "SNS topic ARN for pipeline alarms."
  value       = module.monitoring.alarm_topic_arn
}

output "log_group_name" {
  description = "CloudWatch log group for the consumer."
  value       = module.monitoring.log_group_name
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
