variable "project" {
  type        = string
  description = "Project name prefix for all resources."
  default     = "industrial-ai"
}

variable "region" {
  type        = string
  description = "AWS region for the state backend."
  default     = "ca-central-1"
}

variable "account_suffix" {
  type        = string
  description = "Short, globally-unique suffix for the state bucket name (S3 bucket names are global). No account ID is hardcoded; supply e.g. a 6-char random string."
}
