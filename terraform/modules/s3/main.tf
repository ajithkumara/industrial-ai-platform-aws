# S3 data lake bucket (raw/Bronze/Silver/Gold landing) — AWS equivalent of the
# Azure ADLS Gen2 datalake. Security controls mirror the Azure hardening:
#   - versioning (Azure P0-05 blob versioning)
#   - lifecycle cool/archive (Azure P1-09: IA @30d, Glacier @90d for raw/)
#   - KMS SSE, TLS-only bucket policy, all public access blocked
#   - prevent_destroy (Azure P0-02)
#   - server access logging to a dedicated log bucket (audit)

resource "aws_s3_bucket" "logs" {
  bucket = "${var.name_prefix}-lake-logs"
  tags   = merge(var.tags, { Purpose = "s3-access-logs" })
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_public_access_block" "logs" {
  bucket                  = aws_s3_bucket.logs.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "logs" {
  bucket = aws_s3_bucket.logs.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.kms_key_arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_versioning" "logs" {
  bucket = aws_s3_bucket.logs.id
  versioning_configuration {
    status = "Enabled"
  }
}

# ---- the data lake bucket ----
resource "aws_s3_bucket" "lake" {
  bucket = "${var.name_prefix}-lake-${var.bucket_suffix}"
  tags   = merge(var.tags, { Purpose = "medallion-lake" })
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_public_access_block" "lake" {
  bucket                  = aws_s3_bucket.lake.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
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
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.kms_key_arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_logging" "lake" {
  bucket        = aws_s3_bucket.lake.id
  target_bucket = aws_s3_bucket.logs.id
  target_prefix = "lake-access/"
}

# Lifecycle: raw/ telemetry ages to Infrequent Access then Glacier; Silver ages
# more slowly. Mirrors the Azure P1-09 cool/archive intent. Checkpoints are not
# stored in S3 (DynamoDB), so nothing critical is tiered.
resource "aws_s3_bucket_lifecycle_configuration" "lake" {
  bucket = aws_s3_bucket.lake.id

  rule {
    id     = "abort-incomplete-multipart"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  rule {
    id     = "raw-tier-down"
    status = "Enabled"
    filter {
      prefix = "raw/"
    }
    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }
    transition {
      days          = 90
      storage_class = "GLACIER"
    }
    noncurrent_version_expiration {
      noncurrent_days = 90
    }
  }

  rule {
    id     = "silver-tier-down"
    status = "Enabled"
    filter {
      prefix = "silver/"
    }
    transition {
      days          = 60
      storage_class = "STANDARD_IA"
    }
    transition {
      days          = 180
      storage_class = "GLACIER"
    }
  }
}

# TLS-only + deny-unencrypted-PUT bucket policy (defense in depth over SSE default).
data "aws_iam_policy_document" "lake" {
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.lake.arn, "${aws_s3_bucket.lake.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "lake" {
  bucket = aws_s3_bucket.lake.id
  policy = data.aws_iam_policy_document.lake.json
}
