# Secrets Manager — AWS equivalent of Azure Key Vault. Values are created BLANK
# on purpose (placeholder). Populate out-of-band (console/CLI) or via a
# controlled pipeline; never commit real secret values to the repo.

resource "aws_secretsmanager_secret" "this" {
  for_each    = toset(var.secret_names)
  name        = "${var.name_prefix}/${each.value}"
  kms_key_id  = var.kms_key_arn
  description = "Placeholder secret for ${each.value}. Populate out-of-band; do NOT commit values."
  tags        = var.tags
}

# Intentionally NO aws_secretsmanager_secret_version with a real value here.
# A blank placeholder version is created so the secret exists; operators set the
# real value via:  aws secretsmanager put-secret-value --secret-id <name> --secret-string ...
resource "aws_secretsmanager_secret_version" "placeholder" {
  for_each      = aws_secretsmanager_secret.this
  secret_id     = each.value.id
  secret_string = jsonencode({ placeholder = "REPLACE_OUT_OF_BAND" })

  lifecycle {
    # Never let Terraform overwrite an operator-populated value on future applies.
    ignore_changes = [secret_string]
  }
}
