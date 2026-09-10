# =============================================================================
# Stage 1 — Minimum Viable Ingestion (cost-safe, ephemeral)
# =============================================================================
# Creates ONLY: Kinesis + S3 + DynamoDB + IAM.
# Intentionally skips: KMS CMKs, VPC endpoints, CloudTrail, Secrets Manager,
# ECR, CloudWatch alarms. See COST_WARNING.md.
#
# COST: ~$0.015 for a 1-hour Kinesis shard. S3 + DynamoDB within Free Tier.
# Run `terraform destroy` immediately after testing.
# =============================================================================

locals {
  prefix = "${var.project_prefix}-${var.environment}"
}

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# ---------------------------------------------------------------------------
# S3 — Bronze lake bucket (AWS-managed SSE, no CMK, no access-logging bucket)
# ---------------------------------------------------------------------------
resource "aws_s3_bucket" "lake" {
  # Bucket names must be globally unique. Using account ID + region scopes it.
  bucket        = "${local.prefix}-lake-${data.aws_caller_identity.current.account_id}"
  force_destroy = true # Stage 1: allow destroy even with objects

  lifecycle {
    # Stage 1: force_destroy = true so `terraform destroy` works cleanly.
    # In production (full dev / prod env), set force_destroy = false and
    # add prevent_destroy = true.
  }
}

resource "aws_s3_bucket_versioning" "lake" {
  bucket = aws_s3_bucket.lake.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "lake" {
  bucket = aws_s3_bucket.lake.id
  rule {
    apply_server_side_encryption_by_default {
      # AWS-managed key (free). Upgrade to aws:kms + CMK in full dev env.
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = false
  }
}

resource "aws_s3_bucket_public_access_block" "lake" {
  bucket                  = aws_s3_bucket.lake.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# TLS-only bucket policy
resource "aws_s3_bucket_policy" "lake_tls" {
  bucket = aws_s3_bucket.lake.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyNonTLS"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource = [
        aws_s3_bucket.lake.arn,
        "${aws_s3_bucket.lake.arn}/*",
      ]
      Condition = {
        Bool = { "aws:SecureTransport" = "false" }
      }
    }]
  })
}

# ---------------------------------------------------------------------------
# Kinesis Data Stream — 1 shard, 24h retention, AWS-managed KMS
# 24h retention (default) to avoid the $0.023/shard-hr extended-retention fee.
# Use the full dev env (168h) when you need replay across days.
# ---------------------------------------------------------------------------
resource "aws_kinesis_stream" "telemetry" {
  name             = "${local.prefix}-telemetryhub"
  shard_count      = 1
  retention_period = 24 # hours — free tier; 168h costs extra

  stream_mode_details {
    stream_mode = "PROVISIONED"
  }

  encryption_type = "KMS"
  kms_key_id      = "alias/aws/kinesis" # AWS-managed, no charge for the key itself
}

# ---------------------------------------------------------------------------
# DynamoDB — checkpoint table (on-demand, AWS-managed encryption)
# ---------------------------------------------------------------------------
resource "aws_dynamodb_table" "checkpoints" {
  name         = "${local.prefix}-checkpoints"
  billing_mode = "PAY_PER_REQUEST" # on-demand; Free Tier covers tiny checkpoint volume

  hash_key  = "shard_id"
  range_key = "stream_name"

  attribute {
    name = "shard_id"
    type = "S"
  }

  attribute {
    name = "stream_name"
    type = "S"
  }

  # AWS-managed encryption (free). Use CMK in full dev env for CKV2_AWS_119 compliance.
  server_side_encryption {
    enabled = true
    # kms_key_arn not set → AWS-managed key
  }

  point_in_time_recovery {
    enabled = true
  }
}

# ---------------------------------------------------------------------------
# IAM — consumer role
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "consumer_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "consumer" {
  name               = "${local.prefix}-consumer"
  assume_role_policy = data.aws_iam_policy_document.consumer_assume.json
}

data "aws_iam_policy_document" "consumer_policy" {
  # Kinesis — read from the stream
  statement {
    sid    = "KinesisRead"
    effect = "Allow"
    actions = [
      "kinesis:GetRecords",
      "kinesis:GetShardIterator",
      "kinesis:DescribeStream",
      "kinesis:DescribeStreamSummary",
      "kinesis:ListShards",
      "kinesis:ListStreams",
    ]
    resources = [aws_kinesis_stream.telemetry.arn]
  }

  # Kinesis KMS — decrypt records
  statement {
    sid    = "KinesisKMS"
    effect = "Allow"
    actions = [
      "kms:Decrypt",
      "kms:GenerateDataKey",
    ]
    resources = ["*"] # AWS-managed key ARN is account-specific; * is safe with condition
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["kinesis.${data.aws_region.current.name}.amazonaws.com"]
    }
  }

  # S3 — write raw bronze + DLQ
  statement {
    sid    = "S3Write"
    effect = "Allow"
    actions = [
      "s3:PutObject",
      "s3:GetObject",
      "s3:ListBucket",
    ]
    resources = [
      aws_s3_bucket.lake.arn,
      "${aws_s3_bucket.lake.arn}/*",
    ]
  }

  # DynamoDB — checkpoint read/write
  statement {
    sid    = "DynamoDBCheckpoint"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:DeleteItem",
      "dynamodb:Scan",
      "dynamodb:Query",
    ]
    resources = [aws_dynamodb_table.checkpoints.arn]
  }
}

resource "aws_iam_role_policy" "consumer" {
  name   = "${local.prefix}-consumer-policy"
  role   = aws_iam_role.consumer.id
  policy = data.aws_iam_policy_document.consumer_policy.json
}

# ---------------------------------------------------------------------------
# IAM — producer role
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "producer_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "producer" {
  name               = "${local.prefix}-producer"
  assume_role_policy = data.aws_iam_policy_document.producer_assume.json
}

data "aws_iam_policy_document" "producer_policy" {
  statement {
    sid    = "KinesisWrite"
    effect = "Allow"
    actions = [
      "kinesis:PutRecord",
      "kinesis:PutRecords",
      "kinesis:DescribeStream",
      "kinesis:DescribeStreamSummary",
    ]
    resources = [aws_kinesis_stream.telemetry.arn]
  }

  statement {
    sid    = "KinesisKMS"
    effect = "Allow"
    actions = [
      "kms:GenerateDataKey",
      "kms:Decrypt",
    ]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["kinesis.${data.aws_region.current.name}.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "producer" {
  name   = "${local.prefix}-producer-policy"
  role   = aws_iam_role.producer.id
  policy = data.aws_iam_policy_document.producer_policy.json
}

# ---------------------------------------------------------------------------
# GitHub OIDC CI role (optional — only created when github_org is set)
# ---------------------------------------------------------------------------
resource "aws_iam_openid_connect_provider" "github" {
  count = var.github_org != "" ? 1 : 0

  url = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  # GitHub's OIDC thumbprint (stable; last verified 2024)
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

data "aws_iam_policy_document" "github_oidc_assume" {
  count = var.github_org != "" ? 1 : 0

  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github[0].arn]
    }
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_org}/${var.github_repo}:*"]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "github_ci" {
  count = var.github_org != "" ? 1 : 0

  name               = "${local.prefix}-github-ci"
  assume_role_policy = data.aws_iam_policy_document.github_oidc_assume[0].json
}

# CI role needs S3 + Kinesis + DynamoDB read for tests
data "aws_iam_policy_document" "github_ci_policy" {
  count = var.github_org != "" ? 1 : 0

  statement {
    sid    = "TerraformState"
    effect = "Allow"
    actions = [
      "s3:GetObject", "s3:PutObject", "s3:ListBucket",
      "s3:DeleteObject",
    ]
    resources = [
      # Replace with your bootstrap state bucket ARN after running bootstrap
      "arn:aws:s3:::${var.project_prefix}-tf-state-*",
      "arn:aws:s3:::${var.project_prefix}-tf-state-*/*",
    ]
  }

  statement {
    sid    = "TerraformStateLock"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:DeleteItem",
    ]
    resources = ["arn:aws:dynamodb:*:${data.aws_caller_identity.current.account_id}:table/${var.project_prefix}-tf-lock"]
  }

  statement {
    sid    = "CoreResourcesReadWrite"
    effect = "Allow"
    actions = [
      "kinesis:*", "s3:*", "dynamodb:*",
      "iam:GetRole", "iam:ListRoles",
    ]
    resources = ["*"]
    # Note: tighten to specific ARNs before production use (R1 risk)
  }
}

resource "aws_iam_role_policy" "github_ci" {
  count = var.github_org != "" ? 1 : 0

  name   = "${local.prefix}-github-ci-policy"
  role   = aws_iam_role.github_ci[0].id
  policy = data.aws_iam_policy_document.github_ci_policy[0].json
}
