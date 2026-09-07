variable "name_prefix" {
  type        = string
  description = "Naming prefix (project-environment)."
}
variable "key_aliases" {
  type        = list(string)
  description = "Logical key domains to create (e.g. s3, kinesis, dynamodb, secrets, cloudtrail, ecr)."
  default     = ["s3", "kinesis", "dynamodb", "secrets", "cloudtrail", "ecr"]
}
variable "tags" {
  type    = map(string)
  default = {}
}
