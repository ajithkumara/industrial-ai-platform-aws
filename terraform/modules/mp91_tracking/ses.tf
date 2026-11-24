##############################################################################
# Alert email (Phase 2) — Amazon SES
#
# Sender: alerts@<email_domain>. The domain is proved with DKIM (3 CNAME records at IONOS,
# printed by the `email_dns_records_for_ionos` output); DKIM also keeps mail out of spam.
#
# SES starts in SANDBOX mode: it only delivers to addresses verified in SES. Each address in
# email_test_recipients gets a one-time "verify your address" email from AWS. Before real
# customers, request production access once in the SES console (Account dashboard).
#
# COST: $0.10 per 1,000 emails. Nothing while unused. Disabled entirely when email_domain = "".
##############################################################################

resource "aws_ses_domain_identity" "alerts" {
  count  = var.email_domain != "" ? 1 : 0
  domain = var.email_domain
}

resource "aws_ses_domain_dkim" "alerts" {
  count  = var.email_domain != "" ? 1 : 0
  domain = aws_ses_domain_identity.alerts[0].domain
}

resource "aws_ses_email_identity" "test_recipient" {
  for_each = var.email_domain != "" ? toset(var.email_test_recipients) : toset([])
  email    = each.value
}

locals {
  alert_from = var.email_domain != "" ? "FleetPilot Alerts <alerts@${var.email_domain}>" : ""
}

resource "aws_iam_role_policy" "ses_send" {
  count = var.email_domain != "" ? 1 : 0
  name  = "${var.name_prefix}-mp91-ses-send"
  role  = aws_iam_role.fn.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = ["ses:SendEmail"]
      Resource  = "arn:aws:ses:${var.region}:${data.aws_caller_identity.current.account_id}:identity/*"
      Condition = { StringEquals = { "ses:FromAddress" = "alerts@${var.email_domain}" } }
    }]
  })
}
