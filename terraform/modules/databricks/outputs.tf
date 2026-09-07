output "uc_role_arn" { value = aws_iam_role.uc.arn }
output "catalog_name" { value = databricks_catalog.industrial_ai.name }
output "storage_credential_name" { value = databricks_storage_credential.external.name }
output "external_location_name" { value = databricks_external_location.lake.name }
