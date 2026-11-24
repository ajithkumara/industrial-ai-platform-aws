output "dashboard_url" {
  value = var.custom_domain != "" && var.custom_domain_ready ? "https://${var.custom_domain}/" : "https://${aws_cloudfront_distribution.web.domain_name}/"
}
output "cloudfront_domain" { value = aws_cloudfront_distribution.web.domain_name }
output "api_url" { value = aws_apigatewayv2_api.track.api_endpoint }
output "cognito_login_domain" { value = local.auth_domain }
output "dns_records_for_ionos" {
  description = "Add these at IONOS (DNS for brocodehub.com)."
  value = var.custom_domain == "" ? [] : concat(
    [for o in aws_acm_certificate.web[0].domain_validation_options : {
      purpose = "ACM certificate validation (step 1)"
      type    = o.resource_record_type
      name    = o.resource_record_name
      value   = o.resource_record_value
    }],
    [{
      purpose = "Point the subdomain at CloudFront (step 2)"
      type    = "CNAME"
      name    = var.custom_domain
      value   = aws_cloudfront_distribution.web.domain_name
    }]
  )
}
output "fleet_table" { value = aws_dynamodb_table.fleet.name }
output "fleet_table_arn" { value = aws_dynamodb_table.fleet.arn }

output "email_dns_records_for_ionos" {
  description = "Add these at IONOS so SES can send alert email from the domain (DKIM)."
  value = var.email_domain == "" ? [] : [for t in aws_ses_domain_dkim.alerts[0].dkim_tokens : {
    purpose = "SES DKIM (alert email)"
    type    = "CNAME"
    name    = "${t}._domainkey.${var.email_domain}"
    value   = "${t}.dkim.amazonses.com"
  }]
}
