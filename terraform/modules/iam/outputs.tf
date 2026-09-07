output "consumer_role_arn" { value = aws_iam_role.consumer.arn }
output "producer_role_arn" { value = aws_iam_role.producer.arn }
output "ci_role_arn" {
  value       = try(aws_iam_role.ci[0].arn, null)
  description = "GitHub OIDC CI deploy role ARN (null if OIDC disabled)."
}
