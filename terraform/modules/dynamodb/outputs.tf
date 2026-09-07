output "table_name" {
  value       = aws_dynamodb_table.checkpoints.name
  description = "Checkpoint lease table name."
}
output "table_arn" {
  value       = aws_dynamodb_table.checkpoints.arn
  description = "Checkpoint lease table ARN."
}
