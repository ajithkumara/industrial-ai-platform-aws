# aws-deployment-evidence.md — NOT EXECUTED (requires your AWS account + Databricks)

No live AWS resources were created by this build. Deployment is delivered
deploy-ready. To deploy and capture real evidence:

```
# 1. State backend
cd terraform/bootstrap && terraform init && terraform apply -var account_suffix=<uniq>
# 2. Core infra
cd ../environments/dev
cp backend.hcl.example backend.hcl            # fill from bootstrap outputs
cp terraform.tfvars.example terraform.tfvars  # fill unique suffixes
terraform init -backend-config=backend.hcl && terraform apply
# 3. Verify deployed resources
aws s3 ls && aws kinesis list-streams && aws dynamodb list-tables
# 4. Unity Catalog (after a Databricks workspace exists)
cd ../dev-databricks && cp terraform.tfvars.example terraform.tfvars  # fill from core outputs
terraform init -backend-config=backend.hcl && terraform apply
# 5. Bundle deploy
export DATABRICKS_HOST=... BUNDLE_VAR_s3_bucket=$(terraform -chdir=../environments/dev output -raw s3_bucket)
databricks bundle deploy -t dev
```

Paste `terraform output`, `aws ...`, and `databricks bundle validate` results
back here and this file becomes the real deployment evidence. Nothing is
fabricated until then.
