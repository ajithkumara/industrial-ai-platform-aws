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
