# Databricks on AWS — Unity Catalog governance for the S3 medallion lake.
# AWS-native translation of the Azure reference terraform/modules/databricks
# (which used an Azure Access Connector managed identity + abfss external
# location). Here the storage credential is backed by an IAM role that the
# Databricks control plane assumes to reach S3 — the AWS-native UC pattern.
#
# WORKSPACE PROVISIONING NOTE: creating the Databricks *workspace* itself on
# AWS is an account-level operation (Databricks account API + a cross-account
# IAM role + customer-managed VPC). That is environment/account-specific and is
# left to the account admin / a dedicated workspace module — this module takes
# the workspace as a given (var.databricks_host) and provisions the UC objects
# on top of it, exactly mirroring how the Azure module layered UC on top of the
# azurerm_databricks_workspace. See docs/evidence for the NOT EXECUTED items.

data "aws_caller_identity" "current" {}

# ---- IAM role Databricks assumes for UC S3 access ----
# Trust policy allows the Databricks Unity Catalog AWS account to assume this
# role (with the external-id self-assumption pattern UC requires).
data "aws_iam_policy_document" "uc_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "AWS"
      identifiers = [var.databricks_uc_aws_account_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "sts:ExternalId"
      values   = [var.databricks_uc_external_id]
    }
  }
  # Self-assumption (UC requirement)
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }
    condition {
      test     = "StringEquals"
      variable = "sts:ExternalId"
      values   = [var.databricks_uc_external_id]
    }
  }
}

resource "aws_iam_role" "uc" {
  name               = "${var.name_prefix}-uc-s3-access"
  assume_role_policy = data.aws_iam_policy_document.uc_assume.json
  tags               = var.tags
}

data "aws_iam_policy_document" "uc" {
  statement {
    sid     = "S3DataAccess"
    actions = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket", "s3:GetBucketLocation"]
    resources = [var.s3_bucket_arn, "${var.s3_bucket_arn}/*"]
  }
  statement {
    sid       = "KmsForS3"
    actions   = ["kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey"]
    resources = [var.s3_kms_key_arn]
  }
}

resource "aws_iam_role_policy" "uc" {
  name   = "${var.name_prefix}-uc-s3-access"
  role   = aws_iam_role.uc.id
  policy = data.aws_iam_policy_document.uc.json
}

# ---- Unity Catalog objects (mirror the Azure module 1:1) ----
resource "databricks_storage_credential" "external" {
  name = "${var.name_prefix}-s3-cred"
  aws_iam_role {
    role_arn = aws_iam_role.uc.arn
  }
  comment = "Storage Credential for Industrial AI data lake via IAM role (S3)."
}

resource "databricks_external_location" "lake" {
  name            = "industrial_ai_lake"
  url             = "s3://${var.s3_bucket}/"
  credential_name = databricks_storage_credential.external.name
  comment         = "External Location for Industrial AI Medallion Lakehouse (S3)."
  skip_validation = false
  depends_on      = [databricks_storage_credential.external]
}

resource "databricks_catalog" "industrial_ai" {
  name         = "industrial_ai"
  comment      = "Industrial AI Medallion Data Governance Catalog"
  storage_root = databricks_external_location.lake.url
  depends_on   = [databricks_external_location.lake]
}

# Same schemas as the Azure reference, including the `ml` schema required for
# three-part model registration industrial_ai.ml.<model>.
resource "databricks_schema" "schemas" {
  for_each     = toset(["bronze", "silver", "gold", "serving", "ml"])
  catalog_name = databricks_catalog.industrial_ai.name
  name         = each.value
  comment      = "Schema for ${each.value} layer"
  depends_on   = [databricks_catalog.industrial_ai]
}

data "databricks_current_user" "me" {}

locals {
  effective_principal = var.principal != "" ? var.principal : data.databricks_current_user.me.user_name
}

resource "databricks_grants" "catalog" {
  count   = local.effective_principal != "" ? 1 : 0
  catalog = databricks_catalog.industrial_ai.name
  grant {
    principal  = local.effective_principal
    privileges = ["USE_CATALOG"]
  }
  depends_on = [databricks_catalog.industrial_ai]
}

resource "databricks_grants" "schemas" {
  for_each = local.effective_principal != "" ? databricks_schema.schemas : {}
  schema   = "${databricks_catalog.industrial_ai.name}.${each.key}"
  grant {
    principal  = local.effective_principal
    privileges = ["USE_SCHEMA", "CREATE_TABLE"]
  }
  depends_on = [databricks_schema.schemas]
}

resource "databricks_grants" "external_location" {
  count             = local.effective_principal != "" ? 1 : 0
  external_location = databricks_external_location.lake.name
  grant {
    principal  = local.effective_principal
    privileges = ["READ_FILES", "WRITE_FILES", "CREATE_EXTERNAL_TABLE"]
  }
  depends_on = [databricks_external_location.lake]
}
