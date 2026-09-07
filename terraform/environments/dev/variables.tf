variable "project" {
  type    = string
  default = "industrial-ai"
}
variable "environment" {
  type    = string
  default = "dev"
}
variable "region" {
  type    = string
  default = "ca-central-1"
}
variable "availability_zones" {
  type    = list(string)
  default = ["ca-central-1a", "ca-central-1b"]
}

# Globally-unique S3 suffixes (S3 names are global). No account ID hardcoded.
variable "lake_bucket_suffix" {
  type        = string
  description = "Unique suffix for the data-lake bucket name."
}
variable "cloudtrail_bucket_suffix" {
  type        = string
  description = "Unique suffix for the CloudTrail bucket name."
}

variable "github_repo" {
  type    = string
  default = "ajithkumara/industrial-ai-platform-aws"
}
variable "enable_github_oidc" {
  type    = bool
  default = true
}
variable "alarm_email" {
  type    = string
  default = ""
}
