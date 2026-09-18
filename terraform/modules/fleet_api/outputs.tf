output "api_url" {
  value       = aws_apigatewayv2_stage.default.invoke_url
  description = "Base URL for the Fleet API (e.g. https://xxx.execute-api.ca-central-1.amazonaws.com)"
}

output "api_id" {
  value       = aws_apigatewayv2_api.fleet.id
  description = "API Gateway HTTP API ID."
}

output "lambda_function_name" {
  value       = aws_lambda_function.fleet_api.function_name
  description = "Lambda function name."
}

output "lambda_function_arn" {
  value       = aws_lambda_function.fleet_api.arn
  description = "Lambda function ARN."
}

output "data_endpoint" {
  value       = "${aws_apigatewayv2_stage.default.invoke_url}/data"
  description = "GET this URL to retrieve cached fleet data."
}

output "refresh_endpoint" {
  value       = "${aws_apigatewayv2_stage.default.invoke_url}/refresh"
  description = "GET this URL to trigger Athena refresh (takes 10-30s)."
}
