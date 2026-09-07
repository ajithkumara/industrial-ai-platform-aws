locals {
  name_prefix = "${var.project}-${var.environment}"
  tags        = { Project = var.project, Environment = var.environment, ManagedBy = "Terraform" }
}

module "databricks" {
  source                    = "../../modules/databricks"
  name_prefix               = local.name_prefix
  s3_bucket                 = var.s3_bucket
  s3_bucket_arn             = var.s3_bucket_arn
  s3_kms_key_arn            = var.s3_kms_key_arn
  databricks_uc_external_id = var.databricks_uc_external_id
  principal                 = var.principal
  tags                      = local.tags
}
