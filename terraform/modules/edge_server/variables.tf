variable "name_prefix" {
  description = "Resource name prefix (e.g. iap-dev)"
  type        = string
}

variable "region" {
  description = "AWS region"
  type        = string
  default     = "ca-central-1"
}

variable "vpc_id" {
  description = "VPC ID to place the instance in"
  type        = string
}

variable "subnet_id" {
  description = "Public subnet ID for the EC2 instance (must have internet gateway)"
  type        = string
}

variable "lake_bucket" {
  description = "S3 lake bucket name (telemetry will be written here)"
  type        = string
}

variable "lake_bucket_arn" {
  description = "S3 lake bucket ARN"
  type        = string
}

variable "ssh_allowed_cidrs" {
  description = "CIDR blocks allowed for SSH (leave empty to disable SSH ingress)"
  type        = list(string)
  default     = []
}

variable "key_pair_name" {
  description = "EC2 key pair name for SSH access (leave empty to disable)"
  type        = string
  default     = ""
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}

variable "alarm_email" {
  description = "Email that receives edge-server alarm notifications (SNS). Leave blank to skip; set it in terraform.tfvars."
  type        = string
  default     = ""
}
