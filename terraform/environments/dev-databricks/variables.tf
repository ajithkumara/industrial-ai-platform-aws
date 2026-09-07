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

variable "databricks_host" {
  type        = string
  description = "Databricks-on-AWS workspace URL (from the account console / core outputs)."
}

# These come from the core dev environment outputs (terraform output -raw ...).
variable "s3_bucket" {
  type = string
}
variable "s3_bucket_arn" {
  type = string
}
variable "s3_kms_key_arn" {
  type = string
}

variable "databricks_uc_external_id" {
  type        = string
  description = "Databricks account external ID for the UC role trust (account console)."
}
variable "principal" {
  type    = string
  default = ""
}
