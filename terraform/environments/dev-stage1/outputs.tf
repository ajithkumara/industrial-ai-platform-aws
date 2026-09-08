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
