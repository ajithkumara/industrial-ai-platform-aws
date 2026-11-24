provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "industrial-ai-platform"
      Environment = "dev-stage1"
      ManagedBy   = "terraform"
      CostStage   = "stage1-ephemeral"
    }
  }
}

# CloudFront certificates must live in us-east-1 (used by module.mp91_tracking).
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"

  default_tags {
    tags = {
      Project     = "industrial-ai-platform"
      Environment = "dev-stage1"
      ManagedBy   = "terraform"
      CostStage   = "stage1-ephemeral"
    }
  }
}
