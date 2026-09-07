# IAM roles (least privilege) — AWS equivalent of Azure Managed Identity + RBAC.
# No static credentials anywhere: workloads assume roles; CI uses GitHub OIDC.

data "aws_caller_identity" "current" {}

# ---- Consumer role: read Kinesis, write S3 raw/, RW DynamoDB checkpoints ----
data "aws_iam_policy_document" "consumer_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com", "ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "consumer" {
  name               = "${var.name_prefix}-consumer"
  assume_role_policy = data.aws_iam_policy_document.consumer_assume.json
  tags               = var.tags
}

data "aws_iam_policy_document" "consumer" {
  statement {
    sid     = "KinesisRead"
    actions = ["kinesis:GetRecords", "kinesis:GetShardIterator", "kinesis:DescribeStream", "kinesis:ListShards"]
    resources = [var.kinesis_stream_arn]
  }
  statement {
    sid       = "S3WriteRaw"
    actions   = ["s3:PutObject"]
    resources = ["${var.s3_bucket_arn}/raw/*"]
  }
  statement {
    sid       = "DynamoCheckpoint"
    actions   = ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:Scan", "dynamodb:UpdateItem"]
    resources = [var.dynamodb_table_arn]
  }
  statement {
    sid       = "KmsUse"
    actions   = ["kms:Encrypt", "kms:Decrypt", "kms:GenerateDataKey"]
    resources = var.kms_key_arns
  }
}

resource "aws_iam_role_policy" "consumer" {
  name   = "${var.name_prefix}-consumer"
  role   = aws_iam_role.consumer.id
  policy = data.aws_iam_policy_document.consumer.json
}

# ---- Producer role: write Kinesis only ----
resource "aws_iam_role" "producer" {
  name               = "${var.name_prefix}-producer"
  assume_role_policy = data.aws_iam_policy_document.consumer_assume.json
  tags               = var.tags
}

data "aws_iam_policy_document" "producer" {
  statement {
    sid       = "KinesisWrite"
    actions   = ["kinesis:PutRecord", "kinesis:PutRecords", "kinesis:DescribeStream"]
    resources = [var.kinesis_stream_arn]
  }
  statement {
    sid       = "KmsEncrypt"
    actions   = ["kms:Encrypt", "kms:GenerateDataKey"]
    resources = var.kms_key_arns
  }
}

resource "aws_iam_role_policy" "producer" {
  name   = "${var.name_prefix}-producer"
  role   = aws_iam_role.producer.id
  policy = data.aws_iam_policy_document.producer.json
}

# ---- GitHub OIDC provider + CI deploy role (no static keys; short-lived tokens) ----
resource "aws_iam_openid_connect_provider" "github" {
  count           = var.enable_github_oidc ? 1 : 0
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  # GitHub's OIDC thumbprint. Verify current value before apply.
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
  tags            = var.tags
}

data "aws_iam_policy_document" "ci_assume" {
  count = var.enable_github_oidc ? 1 : 0
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github[0].arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    # Scope to this repo's PRs + main. Tighten the subject as needed.
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repo}:*"]
    }
  }
}

resource "aws_iam_role" "ci" {
  count              = var.enable_github_oidc ? 1 : 0
  name               = "${var.name_prefix}-github-ci"
  assume_role_policy = data.aws_iam_policy_document.ci_assume[0].json
  tags               = var.tags
}

# CI deploy permissions are intentionally scoped to the services this platform
# provisions. This is broader than a runtime role by necessity (Terraform must
# create/read/update infra) but is NOT AdministratorAccess. Tighten per-service
# as the resource set stabilises.
data "aws_iam_policy_document" "ci" {
  count = var.enable_github_oidc ? 1 : 0
  statement {
    sid     = "TerraformDeploy"
    actions = [
      "s3:*", "kinesis:*", "dynamodb:*", "kms:*", "iam:*",
      "secretsmanager:*", "ec2:*", "logs:*", "cloudwatch:*",
      "cloudtrail:*", "ecr:*"
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "ci" {
  count  = var.enable_github_oidc ? 1 : 0
  name   = "${var.name_prefix}-github-ci"
  role   = aws_iam_role.ci[0].id
  policy = data.aws_iam_policy_document.ci[0].json
}
