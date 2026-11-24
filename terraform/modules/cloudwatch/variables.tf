variable "name_prefix" { type = string }
variable "environment" { type = string }
variable "kinesis_stream_name" { type = string }
variable "region" {
  type        = string
  description = "AWS region for dashboard widgets."
  default     = "ca-central-1"
}
variable "log_kms_key_arn" {
  type        = string
  default     = null
  description = "KMS key ARN for log group encryption. Null = AWS-managed (free, dev-safe)."
}
variable "sns_kms_key_id" {
  type        = string
  default     = null
  description = "KMS key id/alias for SNS topic encryption. Null = no encryption (dev-safe)."
}
variable "alarm_email" {
  type        = string
  default     = ""
  description = "Optional email for alarm notifications (leave blank to skip subscription)."
}
variable "tags" {
  type    = map(string)
  default = {}
}
variable "log_retention_days" {
  type        = number
  default     = 365
  description = "CloudWatch log retention. Default 365 (>=1yr, CKV_AWS_338). Lower in dev to cut cost if desired."
}
