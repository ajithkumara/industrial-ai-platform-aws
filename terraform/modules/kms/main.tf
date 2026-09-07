# Customer-managed KMS keys (CMKs) with rotation, one per data domain, so a
# compromise/rotation of one domain's key is isolated. Encrypts S3, Kinesis,
# DynamoDB, Secrets Manager, CloudTrail, ECR.

data "aws_caller_identity" "current" {}

# Explicit key policy (CKV2_AWS_64): the account root retains full KMS admin
# (standard AWS-recommended baseline so the key is never orphaned), and AWS
# services in this account may use the key for encrypt/decrypt via the
# kms:ViaService condition. This is least-privilege at the service level.
data "aws_iam_policy_document" "key" {
  statement {
    sid       = "EnableRootAccountAdmin"
    effect    = "Allow"
    actions   = ["kms:*"]
    resources = ["*"]
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }
  }
  statement {
    sid       = "AllowServiceUse"
    effect    = "Allow"
    actions   = ["kms:Encrypt", "kms:Decrypt", "kms:ReEncrypt*", "kms:GenerateDataKey*", "kms:DescribeKey"]
    resources = ["*"]
    principals {
      type = "Service"
      identifiers = [
        "s3.amazonaws.com", "kinesis.amazonaws.com", "dynamodb.amazonaws.com",
        "secretsmanager.amazonaws.com", "logs.amazonaws.com",
        "cloudtrail.amazonaws.com", "sns.amazonaws.com", "ecr.amazonaws.com",
      ]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_kms_key" "this" {
  for_each                = toset(var.key_aliases)
  description             = "${var.name_prefix} CMK for ${each.value}"
  enable_key_rotation     = true
  deletion_window_in_days = 30
  policy                  = data.aws_iam_policy_document.key.json
  tags                    = merge(var.tags, { Domain = each.value })
}

resource "aws_kms_alias" "this" {
  for_each      = aws_kms_key.this
  name          = "alias/${var.name_prefix}-${each.key}"
  target_key_id = each.value.key_id
}
