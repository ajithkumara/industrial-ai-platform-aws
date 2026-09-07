variable "name_prefix" { type = string }
variable "kms_key_arn" { type = string }
variable "secret_names" {
  type        = list(string)
  description = "Logical secret names to provision (blank placeholders)."
  default     = ["databricks-host", "databricks-token"]
}
variable "tags" {
  type    = map(string)
  default = {}
}
