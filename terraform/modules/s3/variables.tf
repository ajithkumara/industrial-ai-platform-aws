variable "name_prefix" { type = string }
variable "bucket_suffix" {
  type        = string
  description = "Globally-unique suffix (S3 names are global). No account ID hardcoded."
}
variable "kms_key_arn" { type = string }
variable "tags" {
  type    = map(string)
  default = {}
}
