# Remote state in S3 with DynamoDB state locking. The bucket/table are created
# once by terraform/bootstrap. Values are supplied at init time via -backend-config
# (see backend.hcl) so no account-specific bucket name is hardcoded in the repo.
terraform {
  backend "s3" {}
}
