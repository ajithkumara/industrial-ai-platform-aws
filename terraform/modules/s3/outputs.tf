output "bucket" {
  value       = aws_s3_bucket.lake.id
  description = "Data lake bucket name."
}
output "bucket_arn" {
  value       = aws_s3_bucket.lake.arn
  description = "Data lake bucket ARN."
}
output "logs_bucket" {
  value       = aws_s3_bucket.logs.id
  description = "Access-logs bucket name."
}
