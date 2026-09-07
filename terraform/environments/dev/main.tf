locals {
  name_prefix = "${var.project}-${var.environment}"
  tags = {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

module "kms" {
  source      = "../../modules/kms"
  name_prefix = local.name_prefix
  tags        = local.tags
}

module "s3" {
  source        = "../../modules/s3"
  name_prefix   = local.name_prefix
  bucket_suffix = var.lake_bucket_suffix
  kms_key_arn   = module.kms.key_arns["s3"]
  tags          = local.tags
}

module "kinesis" {
  source      = "../../modules/kinesis"
  name_prefix = local.name_prefix
  kms_key_arn = module.kms.key_arns["kinesis"]
  shard_count = 1
  tags        = local.tags
}

module "dynamodb" {
  source      = "../../modules/dynamodb"
  name_prefix = local.name_prefix
  kms_key_arn = module.kms.key_arns["dynamodb"]
  tags        = local.tags
}

module "iam" {
  source             = "../../modules/iam"
  name_prefix        = local.name_prefix
  kinesis_stream_arn = module.kinesis.stream_arn
  s3_bucket_arn      = module.s3.bucket_arn
  dynamodb_table_arn = module.dynamodb.table_arn
  kms_key_arns       = [module.kms.key_arns["s3"], module.kms.key_arns["kinesis"], module.kms.key_arns["dynamodb"]]
  enable_github_oidc = var.enable_github_oidc
  github_repo        = var.github_repo
  tags               = local.tags
}

module "secrets" {
  source      = "../../modules/secrets"
  name_prefix = local.name_prefix
  kms_key_arn = module.kms.key_arns["secrets"]
  tags        = local.tags
}

module "ecr" {
  source      = "../../modules/ecr"
  name_prefix = local.name_prefix
  kms_key_arn = module.kms.key_arns["ecr"]
  tags        = local.tags
}

module "vpc" {
  source             = "../../modules/vpc"
  name_prefix        = local.name_prefix
  availability_zones = var.availability_zones
  log_kms_key_arn    = module.kms.key_arns["cloudtrail"]
  tags               = local.tags
}

module "cloudtrail" {
  source        = "../../modules/cloudtrail"
  name_prefix   = local.name_prefix
  bucket_suffix = var.cloudtrail_bucket_suffix
  kms_key_arn   = module.kms.key_arns["cloudtrail"]
  tags          = local.tags
}

module "cloudwatch" {
  source              = "../../modules/cloudwatch"
  name_prefix         = local.name_prefix
  environment         = var.environment
  kinesis_stream_name = module.kinesis.stream_name
  log_kms_key_arn     = module.kms.key_arns["cloudtrail"]
  sns_kms_key_id      = module.kms.key_ids["secrets"]
  alarm_email         = var.alarm_email
  tags                = local.tags
}
