output "api_gateway_url" {
  description = "API Gateway endpoint URL"
  value       = aws_apigatewayv2_stage.default.invoke_url
}

output "lambda_function_arn" {
  description = "Lambda function ARN"
  value       = aws_lambda_function.payment_reconciliation.arn
}

output "dynamodb_table_name" {
  description = "DynamoDB table name"
  value       = aws_dynamodb_table.payments.name
}

output "sqs_queue_url" {
  description = "SQS payments queue URL"
  value       = aws_sqs_queue.payments_queue.url
}