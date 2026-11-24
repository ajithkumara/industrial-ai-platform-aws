##############################################################################
# MP91 tracking — live dashboard behind a login
#
#   EventBridge (1 min) -> Lambda process: raw/mp91 -> silver day file -> gold/mp91/latest.json
#   Browser -> CloudFront (S3 static site) -> Cognito Hosted UI login (PKCE)
#           -> API Gateway HTTP API (JWT authorizer) -> Lambda api -> gold JSON
#
# COST (approx, single device): Lambda/EventBridge/API GW/Cognito within free
# tier; S3 requests ~ $0.50/mo; CloudFront ~ $0. ACM certificate free.
##############################################################################

terraform {
  required_providers {
    aws = {
      source                = "hashicorp/aws"
      configuration_aliases = [aws.us_east_1]
    }
  }
}

data "aws_caller_identity" "current" {}

locals {
  account_id  = data.aws_caller_identity.current.account_id
  fn_name     = "${var.name_prefix}-mp91"
  use_domain  = var.custom_domain != "" && var.custom_domain_ready
  web_origins = compact([
    "https://${aws_cloudfront_distribution.web.domain_name}",
    local.use_domain ? "https://${var.custom_domain}" : "",
  ])
  auth_domain = "https://${aws_cognito_user_pool_domain.track.domain}.auth.${var.region}.amazoncognito.com"
  app_url     = local.web_origins[length(local.web_origins) - 1]   # custom domain when live, else CloudFront
}

# ── Lambda package: handler + shared parser/gold modules ─────────────────────
data "archive_file" "pkg" {
  type        = "zip"
  output_path = "${path.module}/mp91_lambda.zip"
  source {
    content  = file("${path.root}/../../../lambda/mp91_processor/handler.py")
    filename = "handler.py"
  }
  source {
    content  = file("${path.root}/../../../edge/h02_parser.py")
    filename = "h02_parser.py"
  }
  source {
    content  = file("${path.root}/../../../edge/mp91_gold.py")
    filename = "mp91_gold.py"
  }
  source {
    content  = file("${path.root}/../../../edge/mp91_alerts.py")
    filename = "mp91_alerts.py"
  }
}

# ── Accounts / vehicles / devices / users (single-table, multi-tenant) ──────
resource "aws_dynamodb_table" "fleet" {
  name         = "${var.name_prefix}-fleet"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "PK"
  range_key    = "SK"
  attribute {
    name = "PK"
    type = "S"
  }
  attribute {
    name = "SK"
    type = "S"
  }
  point_in_time_recovery {
    enabled = true # customer/account data: recoverable to any second in the last 35 days
  }
  # Live-position and "someone is watching" items expire on their own (DEVICE#<id> / LIVE and WATCH).
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }
  tags = var.tags
}

resource "aws_iam_role" "fn" {
  name = "${local.fn_name}-role"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
  tags = var.tags
}

resource "aws_iam_role_policy" "fn" {
  name = "${local.fn_name}-policy"
  role = aws_iam_role.fn.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:${var.region}:${local.account_id}:log-group:/aws/lambda/${local.fn_name}-*:*"
      },
      {
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = var.lake_bucket_arn
        Condition = { StringLike = { "s3:prefix" = ["raw/mp91/*", "silver/mp91/*", "gold/mp91/*", "gold/accounts/*"] } }
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = ["${var.lake_bucket_arn}/raw/mp91/*", "${var.lake_bucket_arn}/silver/mp91/*", "${var.lake_bucket_arn}/gold/mp91/*", "${var.lake_bucket_arn}/gold/accounts/*"]
      },
      {
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = ["${var.lake_bucket_arn}/silver/mp91/*", "${var.lake_bucket_arn}/gold/mp91/*", "${var.lake_bucket_arn}/gold/accounts/*", "${var.lake_bucket_arn}/quarantine/mp91/*"]
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:Query", "dynamodb:Scan"]
        Resource = aws_dynamodb_table.fleet.arn
      },
      {
        # DEVICE#<id>: WATCH flag (GET /live) and ALERTSTATE; ACCOUNT#<aid>: ALERT# items and ALERTSETTINGS.
        # Never USER# items: a login can't be re-pointed at another account by this code path.
        Effect    = "Allow"
        Action    = ["dynamodb:PutItem"]
        Resource  = aws_dynamodb_table.fleet.arn
        Condition = { "ForAllValues:StringLike" = { "dynamodb:LeadingKeys" = ["DEVICE#*", "ACCOUNT#*"] } }
      },
    ]
  })
}

resource "aws_cloudwatch_log_group" "process" {
  name              = "/aws/lambda/${local.fn_name}-process"
  retention_in_days = 14
  tags              = var.tags
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${local.fn_name}-api"
  retention_in_days = 14
  tags              = var.tags
}

resource "aws_lambda_function" "process" {
  function_name    = "${local.fn_name}-process"
  role             = aws_iam_role.fn.arn
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "handler.process"
  filename         = data.archive_file.pkg.output_path
  source_code_hash = data.archive_file.pkg.output_base64sha256
  timeout          = 60
  memory_size      = 256
  environment {
    variables = { LAKE_BUCKET = var.lake_bucket, FLEET_TABLE = aws_dynamodb_table.fleet.name, GOLD_DAYS = "7", PASSES = "4", PASS_SECONDS = "15", ALERT_EMAIL_FROM = local.alert_from, APP_URL = local.app_url }
  }
  depends_on = [aws_cloudwatch_log_group.process]
  tags       = var.tags
}

resource "aws_lambda_function" "api" {
  function_name    = "${local.fn_name}-api"
  role             = aws_iam_role.fn.arn
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "handler.api"
  filename         = data.archive_file.pkg.output_path
  source_code_hash = data.archive_file.pkg.output_base64sha256
  timeout          = 10
  memory_size      = 256
  environment {
    variables = { LAKE_BUCKET = var.lake_bucket, FLEET_TABLE = aws_dynamodb_table.fleet.name }
  }
  depends_on = [aws_cloudwatch_log_group.api]
  tags       = var.tags
}

# ── 1-minute schedule ────────────────────────────────────────────────────────
resource "aws_cloudwatch_event_rule" "every_minute" {
  name                = "${local.fn_name}-every-minute"
  schedule_expression = "rate(1 minute)"
  tags                = var.tags
}

resource "aws_cloudwatch_event_target" "process" {
  rule = aws_cloudwatch_event_rule.every_minute.name
  arn  = aws_lambda_function.process.arn
}

resource "aws_lambda_permission" "events" {
  statement_id  = "AllowEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.process.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.every_minute.arn
}

# ── Cognito: one admin-created user, Hosted UI, code + PKCE ─────────────────
resource "aws_cognito_user_pool" "track" {
  name                     = "${var.name_prefix}-track"
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]
  admin_create_user_config {
    allow_admin_create_user_only = true # no public sign-up
  }
  password_policy {
    minimum_length    = 12
    require_lowercase = true
    require_uppercase = true
    require_numbers   = true
    require_symbols   = false
  }
  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }
  tags = var.tags
}

resource "aws_cognito_user_pool_domain" "track" {
  domain       = "${var.name_prefix}-track-${local.account_id}"
  user_pool_id = aws_cognito_user_pool.track.id
}

resource "aws_cognito_user_pool_client" "web" {
  name                                 = "${var.name_prefix}-track-web"
  user_pool_id                         = aws_cognito_user_pool.track.id
  generate_secret                      = false
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email"]
  supported_identity_providers         = ["COGNITO"]
  callback_urls                        = [for o in local.web_origins : "${o}/"]
  logout_urls                          = [for o in local.web_origins : "${o}/"]
  explicit_auth_flows                  = ["ALLOW_REFRESH_TOKEN_AUTH", "ALLOW_USER_SRP_AUTH"]
  prevent_user_existence_errors        = "ENABLED"
  refresh_token_validity               = 30
  token_validity_units {
    refresh_token = "days"
  }
}

resource "aws_cognito_user" "admin" {
  user_pool_id             = aws_cognito_user_pool.track.id
  username                 = var.admin_email
  desired_delivery_mediums = ["EMAIL"] # Cognito emails a temporary password
  attributes = {
    email          = var.admin_email
    email_verified = "true"
  }
  lifecycle {
    ignore_changes = [attributes]
  }
}

# ── API: GET /mp91 with JWT authorizer ──────────────────────────────────────
resource "aws_apigatewayv2_api" "track" {
  name          = "${var.name_prefix}-track-api"
  protocol_type = "HTTP"
  cors_configuration {
    allow_origins = local.web_origins
    allow_methods = ["GET", "PUT", "OPTIONS"]
    allow_headers = ["authorization", "content-type"]
    max_age       = 3600
  }
  tags = var.tags
}

resource "aws_apigatewayv2_authorizer" "jwt" {
  api_id           = aws_apigatewayv2_api.track.id
  name             = "cognito"
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]
  jwt_configuration {
    issuer   = "https://cognito-idp.${var.region}.amazonaws.com/${aws_cognito_user_pool.track.id}"
    audience = [aws_cognito_user_pool_client.web.id]
  }
}

resource "aws_apigatewayv2_integration" "api" {
  api_id                 = aws_apigatewayv2_api.track.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.api.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "mp91" {
  api_id             = aws_apigatewayv2_api.track.id
  route_key          = "GET /mp91"
  target             = "integrations/${aws_apigatewayv2_integration.api.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.jwt.id
}

# GET /live: latest moving position(s) for the caller's account; also flags "someone is watching"
resource "aws_apigatewayv2_route" "live" {
  api_id             = aws_apigatewayv2_api.track.id
  route_key          = "GET /live"
  target             = "integrations/${aws_apigatewayv2_integration.api.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.jwt.id
}

# Alerts (Phase 2): list recent alerts, read/save the account's alert settings. Same Lambda, same JWT.
resource "aws_apigatewayv2_route" "alerts" {
  for_each           = toset(["GET /alerts", "GET /alert-settings", "PUT /alert-settings"])
  api_id             = aws_apigatewayv2_api.track.id
  route_key          = each.value
  target             = "integrations/${aws_apigatewayv2_integration.api.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.jwt.id
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.track.id
  name        = "$default"
  auto_deploy = true
  default_route_settings {
    throttling_burst_limit = 20
    throttling_rate_limit  = 10
  }
  tags = var.tags
}

resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.track.execution_arn}/*/*"
}

# ── Static site: private S3 + CloudFront (OAC) ──────────────────────────────
resource "aws_s3_bucket" "web" {
  bucket        = "${var.name_prefix}-track-web-${local.account_id}"
  force_destroy = true
  tags          = var.tags
}

resource "aws_s3_bucket_public_access_block" "web" {
  bucket                  = aws_s3_bucket.web.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_cloudfront_origin_access_control" "web" {
  name                              = "${var.name_prefix}-track-web"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_acm_certificate" "web" {
  count             = var.custom_domain != "" ? 1 : 0
  provider          = aws.us_east_1 # CloudFront requires us-east-1 certificates
  domain_name       = var.custom_domain
  validation_method = "DNS"
  tags              = var.tags
  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_acm_certificate_validation" "web" {
  count           = local.use_domain ? 1 : 0
  provider        = aws.us_east_1
  certificate_arn = aws_acm_certificate.web[0].arn
}

resource "aws_cloudfront_distribution" "web" {
  enabled             = true
  default_root_object = "index.html"
  price_class         = "PriceClass_100"
  aliases             = local.use_domain ? [var.custom_domain] : []
  comment             = "MP91 tracking dashboard"

  origin {
    domain_name              = aws_s3_bucket.web.bucket_regional_domain_name
    origin_id                = "web"
    origin_access_control_id = aws_cloudfront_origin_access_control.web.id
  }

  default_cache_behavior {
    target_origin_id       = "web"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true
    cache_policy_id        = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad" # AWS managed: CachingDisabled (tiny site, always fresh)
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = !local.use_domain
    acm_certificate_arn            = local.use_domain ? aws_acm_certificate_validation.web[0].certificate_arn : null
    ssl_support_method             = local.use_domain ? "sni-only" : null
    minimum_protocol_version       = local.use_domain ? "TLSv1.2_2021" : null
  }

  tags = var.tags
}

resource "aws_s3_bucket_policy" "web" {
  bucket = aws_s3_bucket.web.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "cloudfront.amazonaws.com" }
      Action    = "s3:GetObject"
      Resource  = "${aws_s3_bucket.web.arn}/*"
      Condition = { StringEquals = { "AWS:SourceArn" = aws_cloudfront_distribution.web.arn } }
    }]
  })
}

locals {
  # Legacy single-page dashboard, or the FleetPilot React build (run `npm run build` with
  # VITE_ROUTER=hash in fleetpilot-web first) when var.use_fleetpilot_web = true.
  web_dir = var.use_fleetpilot_web ? "${path.root}/../../../fleetpilot-web/dist" : "${path.root}/../../../dashboard/web"
  legacy_files = {
    "index.html"    = "text/html"
    "manifest.json" = "application/manifest+json"
    "icon.svg"      = "image/svg+xml"
  }
  mime = {
    html = "text/html", js = "application/javascript", css = "text/css", svg = "image/svg+xml", json = "application/json",
    png = "image/png", ico = "image/x-icon", woff2 = "font/woff2", woff = "font/woff", map = "application/json", txt = "text/plain",
  }
  # config.js is written below from Terraform outputs, so it is excluded from the build copy.
  static_files = var.use_fleetpilot_web ? {
    for f in fileset(local.web_dir, "**") : f => lookup(local.mime, reverse(split(".", f))[0], "application/octet-stream") if f != "config.js"
  } : local.legacy_files
}

resource "aws_s3_object" "static" {
  for_each     = local.static_files
  bucket       = aws_s3_bucket.web.id
  key          = each.key
  source       = "${local.web_dir}/${each.key}"
  etag         = filemd5("${local.web_dir}/${each.key}")
  content_type = each.value
}

# config.js — no secrets: the client id and endpoints are public by design.
resource "aws_s3_object" "config" {
  bucket       = aws_s3_bucket.web.id
  key          = "config.js"
  content_type = "application/javascript"
  content      = <<-JS
    window.TRACK_CONFIG = {
      apiUrl: "${aws_apigatewayv2_api.track.api_endpoint}",
      authDomain: "${local.auth_domain}",
      clientId: "${aws_cognito_user_pool_client.web.id}",
      redirectUri: location.origin + "/"
    };
  JS
}
