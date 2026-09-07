variable "name_prefix" { type = string }
variable "environment" { type = string }
variable "kinesis_stream_name" { type = string }
variable "log_kms_key_arn" { type = string }
variable "sns_kms_key_id" {
  type        = string
  description = "KMS key id/alias for SNS topic encryption."
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
