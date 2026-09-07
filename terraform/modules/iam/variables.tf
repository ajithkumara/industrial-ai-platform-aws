variable "name_prefix" { type = string }
variable "kinesis_stream_arn" { type = string }
variable "s3_bucket_arn" { type = string }
variable "dynamodb_table_arn" { type = string }
variable "kms_key_arns" { type = list(string) }
variable "enable_github_oidc" {
  type    = bool
  default = true
}
variable "github_repo" {
  type        = string
  description = "GitHub org/repo for OIDC subject scoping, e.g. ajithkumara/industrial-ai-platform-aws."
  default     = "ajithkumara/industrial-ai-platform-aws"
}
variable "tags" {
  type    = map(string)
  default = {}
}
