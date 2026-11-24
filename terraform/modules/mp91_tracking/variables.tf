variable "name_prefix" { type = string }
variable "region" { type = string }
variable "lake_bucket" { type = string }
variable "lake_bucket_arn" { type = string }
variable "device_id" {
  type    = string
  default = "7018532019"
}
variable "admin_email" {
  description = "Login email for the dashboard. Cognito emails a temporary password to it."
  type        = string
}
variable "custom_domain" {
  description = "e.g. track.brocodehub.com. Empty = CloudFront URL only."
  type        = string
  default     = ""
}
variable "custom_domain_ready" {
  description = "Set true AFTER the ACM validation CNAME is added at the DNS provider (IONOS)."
  type        = bool
  default     = false
}
variable "use_fleetpilot_web" {
  description = "Publish the FleetPilot React build (fleetpilot-web/dist) instead of the legacy dashboard/web page."
  type        = bool
  default     = false
}
variable "tags" {
  type    = map(string)
  default = {}
}

variable "email_domain" {
  description = "Domain alert emails are sent from (alerts@<domain>). Blank = email alerts off."
  type        = string
  default     = ""
}

variable "email_test_recipients" {
  description = "Addresses to verify in SES while the account is in sandbox mode (only these can receive mail)."
  type        = list(string)
  default     = []
}
