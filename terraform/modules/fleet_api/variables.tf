variable "name_prefix" {
  type        = string
  description = "Prefix for all resource names."
}

variable "environment" {
  type        = string
  description = "Deployment environment."
}

variable "region" {
  type        = string
  default     = "ca-central-1"
}

variable "lake_bucket" {
  type        = string
  description = "S3 data lake bucket name."
}

variable "lake_bucket_arn" {
  type        = string
  description = "ARN of the data lake S3 bucket."
}

variable "athena_results_bucket" {
  type        = string
  description = "S3 bucket where Athena writes results."
}

variable "athena_results_bucket_arn" {
  type        = string
  description = "ARN of the Athena results bucket."
}

variable "athena_database" {
  type        = string
  description = "Glue catalog database name."
}

variable "athena_table" {
  type        = string
  description = "Glue catalog table name."
}

variable "athena_workgroup" {
  type        = string
  description = "Athena workgroup name."
}

variable "lambda_timeout" {
  type        = number
  description = "Lambda timeout in seconds (refresh queries can take 30s)."
  default     = 60
}

variable "lambda_memory" {
  type        = number
  default     = 256
}

variable "tags" {
  type    = map(string)
  default = {}
}
