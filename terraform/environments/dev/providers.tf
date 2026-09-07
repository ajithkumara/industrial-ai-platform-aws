# Region from variable; credentials come from the ambient environment — locally
# via `aws sso login` / a named profile, in CI via GitHub OIDC -> IAM role
# (aws-actions/configure-aws-credentials). NO static keys are configured here.
provider "aws" {
  region = var.region
  default_tags {
    tags = {
      Project     = var.project
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}
