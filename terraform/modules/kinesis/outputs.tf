output "stream_name" {
  value       = aws_kinesis_stream.this.name
  description = "Kinesis stream name."
}
output "stream_arn" {
  value       = aws_kinesis_stream.this.arn
  description = "Kinesis stream ARN."
}
