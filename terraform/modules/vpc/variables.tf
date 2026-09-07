variable "name_prefix" { type = string }
variable "cidr_block" {
  type    = string
  default = "10.20.0.0/16"
}
variable "private_subnet_cidrs" {
  type    = list(string)
  default = ["10.20.1.0/24", "10.20.2.0/24"]
}
variable "availability_zones" {
  type        = list(string)
  description = "AZs for the private subnets (must match region)."
  default     = ["ca-central-1a", "ca-central-1b"]
}
variable "log_kms_key_arn" { type = string }
variable "tags" {
  type    = map(string)
  default = {}
}
variable "log_retention_days" {
  type    = number
  default = 365
}
