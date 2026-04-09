terraform{
    required_providers{
        aws = {
            source = "hashicorp/aws"
            version = "~> 5.0"
        }
    }
}
provider "aws" {
    region = var.aws_region
}

#DynamoDB Table
resource "aws_dynamodb_table" "payments" {
    name = "payments"
    billing_mode = "PAY_PER_REQUEST"
    hash_key = "payment_id"

    attribute{
        name = "reference_id"
        type = 'S'
    }

    global_secondary_index{
        name = "reference_id-index"
        hash_key = "reference_id"
        projection type = "ALL"
    }

    tags= {
        Project = "payment-reconciliation"
    }
}

#SQS Queue
resource "aws_sqs_queue" "payments_dlq"{
    name = "payments_dlq"
}

# IAM Role for Lambda
resource "aws_iam_role" "lambda_role" {
  name = "payment-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_dynamodb" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess"
}

resource "aws_iam_role_policy_attachment" "lambda_sqs" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSQSFullAccess"
}

resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchLogsFullAccess"
}

# Lambda Function
resource "aws_lambda_function" "payment_reconciliation" {
  filename         = "../deployment.zip"
  function_name    = "payment-reconciliation"
  role             = aws_iam_role.lambda_role.arn
  handler          = "src.handlers.payment_handler.handler"
  runtime          = "python3.12"
  source_code_hash = filebase64sha256("../deployment.zip")
  timeout          = 30

  environment {
    variables = {
      DYNAMODB_TABLE_NAME = "payments"
    }
  }
}

# API Gateway
resource "aws_apigatewayv2_api" "payment_api" {
  name          = "payment-reconciliation-api"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "lambda_integration" {
  api_id             = aws_apigatewayv2_api.payment_api.id
  integration_type   = "AWS_PROXY"
  integration_uri    = aws_lambda_function.payment_reconciliation.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "proxy_route" {
  api_id    = aws_apigatewayv2_api.payment_api.id
  route_key = "ANY /{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.lambda_integration.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.payment_api.id
  name        = "$default"
  auto_deploy = true
}

resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.payment_reconciliation.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.payment_api.execution_arn}/*/*"
}