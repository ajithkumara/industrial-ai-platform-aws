variable "aws_region" {
  type        = string
  description = "AWS region to deploy Stage 1 resources."
  default     = "ca-central-1"
}

variable "project_prefix" {
  type        = string
  description = "Short prefix for resource names (e.g. 'iap' for industrial-ai-platform)."
  default     = "iap"
}

variable "environment" {
  type        = string
  description = "Environment label used in resource names."
  default     = "dev"
}

# ---------------------------------------------------------------------------
# GitHub OIDC — only needed if you want the CI IAM role in Stage 1.
# Leave blank to skip creating the OIDC provider + CI role.
# ---------------------------------------------------------------------------
variable "github_org" {
  type        = string
  description = "GitHub organisation or username (e.g. 'your-github-username')."
  default     = ""
}

variable "github_repo" {
  type        = string
  description = "GitHub repository name (e.g. 'industrial-ai-platform-aws')."
  default     = ""
}

# ---------------------------------------------------------------------------
# Cost switches
# ---------------------------------------------------------------------------
variable "enable_kinesis" {
  type        = bool
  description = "Create the Kinesis stream + Kinesis CloudWatch alarms/dashboard. ~$12/month while it exists. Keep false unless running the streaming demo."
  default     = false
}

# ---------------------------------------------------------------------------
# MP91 tracking dashboard
# ---------------------------------------------------------------------------
variable "tracking_admin_email" {
  type        = string
  description = "Login email for the tracking dashboard (Cognito sends a temporary password)."
  default     = "aakumara@gmail.com"
}

variable "tracking_domain" {
  type        = string
  description = "Custom domain for the dashboard, e.g. track.brocodehub.com. Empty = CloudFront URL only."
  default     = ""
}

variable "use_fleetpilot_web" {
  type        = bool
  description = "Publish the FleetPilot React app (build fleetpilot-web first: VITE_ROUTER=hash npm run build)."
  default     = false
}

variable "tracking_domain_ready" {
  type        = bool
  description = "Set true after the ACM validation CNAME has been added at IONOS."
  default     = false
}

variable "alarm_email" {
  description = "Email for edge-server alarm notifications. Leave blank here; set in terraform.tfvars (not a secret, but personal)."
  type        = string
  default     = ""
}

variable "alert_email_domain" {
  description = "Domain for alert email (e.g. brocodehub.com). Blank = email alerts off. Set in terraform.tfvars."
  type        = string
  default     = ""
}

variable "alert_email_test_recipients" {
  description = "SES sandbox: addresses allowed to receive alert email until production access is granted."
  type        = list(string)
  default     = []
}
