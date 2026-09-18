##############################################################################
# Fleet API module — Lambda function + API Gateway HTTP API
##############################################################################

# ── Package Lambda code ───────────────────────────────────────────────────────
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_file = "${path.root}/../../../lambda/fleet_api/handler.py"
  output_path = "${path.module}/fleet_api_lambda.zip"
}

# ── IAM role for Lambda ───────────────────────────────────────────────────────
resource "aws_iam_role" "fleet_api" {
  name = "${var.name_prefix}-fleet-api-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "fleet_api" {
  name = "${var.name_prefix}-fleet-api-policy"
  role = aws_iam_role.fleet_api.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # CloudWatch Logs
      {
        Effect = "Allow"
        Action = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:${var.region}:*:log-group:/aws/lambda/${var.name_prefix}-fleet-api:*"
      },
      # S3 — read lake, write cache, read/write results
      {
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:PutObject", "s3:ListBucket"]
        Resource = [
          var.lake_bucket_arn,
          "${var.lake_bucket_arn}/*",
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetBucketLocation",
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket",
          "s3:ListBucketMultipartUploads",
          "s3:ListMultipartUploadParts",
          "s3:AbortMultipartUpload",
        ]
        Resource = [
          var.athena_results_bucket_arn,
          "${var.athena_results_bucket_arn}/*",
        ]
      },
      # Athena
      {
        Effect = "Allow"
        Action = [
          "athena:StartQueryExecution",
          "athena:GetQueryExecution",
          "athena:GetQueryResults",
          "athena:StopQueryExecution",
          "athena:ListQueryExecutions",
        ]
        Resource = "*"
      },
      # Glue (Athena uses Glue catalog)
      {
        Effect = "Allow"
        Action = [
          "glue:GetDatabase",
          "glue:GetTable",
          "glue:GetPartitions",
          "glue:BatchCreatePartition",
          "glue:CreatePartition",
          "glue:UpdatePartition",
        ]
        Resource = "*"
      },
    ]
  })
}

# ── Lambda function ───────────────────────────────────────────────────────────
resource "aws_lambda_function" "fleet_api" {
  function_name    = "${var.name_prefix}-fleet-api"
  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  role             = aws_iam_role.fleet_api.arn
  timeout          = var.lambda_timeout
  memory_size      = var.lambda_memory

  environment {
    variables = {
      LAKE_BUCKET    = var.lake_bucket
      ATHENA_DB      = var.athena_database
      ATHENA_TABLE   = var.athena_table
      ATHENA_WG      = var.athena_workgroup
      RESULTS_BUCKET = var.athena_results_bucket
      CACHE_KEY      = "processed/dashboard_cache.json"
    }
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-fleet-api" })
}

resource "aws_cloudwatch_log_group" "fleet_api" {
  name              = "/aws/lambda/${aws_lambda_function.fleet_api.function_name}"
  retention_in_days = 7
  tags              = var.tags
}

# ── API Gateway HTTP API ──────────────────────────────────────────────────────
resource "aws_apigatewayv2_api" "fleet" {
  name          = "${var.name_prefix}-fleet-api"
  protocol_type = "HTTP"
  description   = "IAP Fleet Operations REST API"

  cors_configuration {
    allow_origins = ["*"]
    allow_methods = ["GET", "OPTIONS"]
    allow_headers = ["Content-Type", "Authorization"]
    max_age       = 300
  }

  tags = var.tags
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.fleet.id
  name        = "$default"
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.apigw.arn
    format = jsonencode({
      requestId      = "$context.requestId"
      sourceIp       = "$context.identity.sourceIp"
      httpMethod     = "$context.httpMethod"
      routeKey       = "$context.routeKey"
      status         = "$context.status"
      responseLength = "$context.responseLength"
      errorMessage   = "$context.error.message"
    })
  }

  tags = var.tags
}

resource "aws_cloudwatch_log_group" "apigw" {
  name              = "/aws/apigateway/${var.name_prefix}-fleet-api"
  retention_in_days = 7
  tags              = var.tags
}

# Lambda integration
resource "aws_apigatewayv2_integration" "fleet_lambda" {
  api_id             = aws_apigatewayv2_api.fleet.id
  integration_type   = "AWS_PROXY"
  integration_uri    = aws_lambda_function.fleet_api.invoke_arn
  payload_format_version = "2.0"
}

# Routes
resource "aws_apigatewayv2_route" "data" {
  api_id    = aws_apigatewayv2_api.fleet.id
  route_key = "GET /data"
  target    = "integrations/${aws_apigatewayv2_integration.fleet_lambda.id}"
}

resource "aws_apigatewayv2_route" "refresh" {
  api_id    = aws_apigatewayv2_api.fleet.id
  route_key = "GET /refresh"
  target    = "integrations/${aws_apigatewayv2_integration.fleet_lambda.id}"
}

resource "aws_apigatewayv2_route" "health" {
  api_id    = aws_apigatewayv2_api.fleet.id
  route_key = "GET /health"
  target    = "integrations/${aws_apigatewayv2_integration.fleet_lambda.id}"
}

# Grant API Gateway permission to invoke Lambda
resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.fleet_api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.fleet.execution_arn}/*/*"
}
