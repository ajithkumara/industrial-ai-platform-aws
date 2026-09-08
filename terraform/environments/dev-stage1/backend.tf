# Remote state for Stage 1.
# After running bootstrap, copy backend.hcl.example -> backend.hcl and fill in values.
# Then initialise with: terraform init -backend-config=backend.hcl
#
# Alternatively, use local state for Stage 1 (safe since it's ephemeral):
#   terraform init   (no -backend-config; local .tfstate only)
#
# Local state is fine for Stage 1 — just don't commit the .tfstate file.
terraform {
  backend "s3" {}
}
