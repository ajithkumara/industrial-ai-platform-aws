variable "name_prefix" { type = string }
variable "kms_key_arn" { type = string }
variable "shard_count" {
  type        = number
  default     = 1
  description = "Provisioned shard count. Dev=1; scale for production throughput."
}
variable "retention_hours" {
  type        = number
  default     = 168
  description = "Stream retention in hours (168 = 7 days, Azure Event Hub parity)."
}
variable "tags" {
  type    = map(string)
  default = {}
}
