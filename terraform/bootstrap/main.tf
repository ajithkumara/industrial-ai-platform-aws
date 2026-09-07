# One-time bootstrap of the Terraform remote-state backend.
# Creates the S3 state bucket (versioned, KMS-encrypted, public access blocked)
# and the DynamoDB state-lock table. Run ONCE with local state by a privileged
# identity; thereafter every environment uses this backend.
#
#   cd terraform/bootstrap
#   terraform init && terraform apply
#
# No account IDs or personal paths are hardcoded — everything derives from
# variables + the caller's own credentials/region.

terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region
}

locals {
  state_bucket = "${var.project}-tfstate-${var.account_suffix}"
  lock_table   = "${var.project}-tflock"
  tags = {
    Project   = var.project
    ManagedBy = "Terraform"
    Component = "tf-backend"
  }
}

resource "aws_s3_bucket" "state" {
  bucket = local.state_bucket
  tags   = local.tags

  # prevent_destroy: destroying the state bucket orphans every environment's
  # state. Must be removed deliberately.
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_dynamodb_table" "lock" {
  name         = local.lock_table
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"
  attribute {
    name = "LockID"
    type = "S"
  }
  point_in_time_recovery {
    enabled = true
  }
  server_side_encryption {
    enabled = true
  }
  tags = local.tags
}
