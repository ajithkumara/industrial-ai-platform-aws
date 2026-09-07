output "state_bucket" {
  value       = aws_s3_bucket.state.id
  description = "Name of the Terraform remote-state S3 bucket."
}

output "lock_table" {
  value       = aws_dynamodb_table.lock.name
  description = "Name of the Terraform state-lock DynamoDB table."
}
