variable "name_prefix" { type = string }
variable "s3_bucket" { type = string }
variable "s3_bucket_arn" { type = string }
variable "s3_kms_key_arn" { type = string }

variable "databricks_uc_aws_account_arn" {
  type        = string
  description = "The Databricks Unity Catalog AWS account principal ARN that assumes the UC role. From Databricks docs / account console (not secret)."
  default     = "arn:aws:iam::414351767826:role/unity-catalog-prod-UCMasterRole-14S5ZJVKOTYTL"
}
variable "databricks_uc_external_id" {
  type        = string
  description = "Databricks account external ID for the UC role trust (from the Databricks account console). Supply via tfvars; not committed."
}
variable "principal" {
  type    = string
  default = ""
}
variable "tags" {
  type    = map(string)
  default = {}
}
