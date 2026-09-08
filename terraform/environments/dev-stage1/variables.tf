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
