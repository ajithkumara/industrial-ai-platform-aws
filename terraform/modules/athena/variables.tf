variable "name_prefix" {
  type        = string
  description = "Prefix for all resource names."
}

variable "environment" {
  type        = string
  description = "Deployment environment (e.g. dev-stage1)."
}

variable "region" {
  type        = string
  description = "AWS region."
  default     = "ca-central-1"
}

variable "lake_bucket" {
  type        = string
  description = "S3 bucket name for the data lake (telemetry lives here)."
}

variable "lake_bucket_arn" {
  type        = string
  description = "ARN of the data lake bucket (for IAM policies)."
}

variable "tags" {
  type    = map(string)
  default = {}
}
