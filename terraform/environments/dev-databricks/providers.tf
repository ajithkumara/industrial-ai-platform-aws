# Applied as a SECOND pass, after the core dev environment and after a
# Databricks workspace exists (workspace creation is account-level — see the
# databricks module header). Mirrors the Azure repo's standalone
# terraform/unity_catalog/dev composition.
provider "aws" {
  region = var.region
}

# Databricks auth via env: DATABRICKS_HOST + DATABRICKS_TOKEN (or a profile /
# OAuth SP). NO token is committed here.
provider "databricks" {
  host = var.databricks_host
}
