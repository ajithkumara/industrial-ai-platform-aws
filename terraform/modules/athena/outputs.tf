output "database_name" {
  value       = aws_glue_catalog_database.fleet.name
  description = "Glue catalog database name."
}

output "table_name" {
  value       = aws_glue_catalog_table.telemetry.name
  description = "Glue catalog table name (telemetry)."
}

output "workgroup_name" {
  value       = aws_athena_workgroup.fleet.name
  description = "Athena workgroup name."
}

output "results_bucket" {
  value       = aws_s3_bucket.athena_results.bucket
  description = "S3 bucket for Athena query results."
}

output "results_bucket_arn" {
  value       = aws_s3_bucket.athena_results.arn
  description = "ARN of the Athena results bucket."
}
