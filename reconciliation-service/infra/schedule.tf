# Expected cash: an EventBridge schedule invokes the same Lambda, which polls the
# settlement-service event feed from its durable cursor (lambda_entry.handler,
# branch source == "aws.events").

variable "settlement_api_url" {
  type        = string
  description = "Base URL of the settlement-service event feed."
  default     = "http://settlement-service.internal:8080"
}

variable "recon_tenant" {
  type        = string
  description = "Tenant whose settlements this deployment reconciles."
  default     = "acme"
}

variable "poll_schedule" {
  type        = string
  description = "How often the settlement feed is polled."
  default     = "rate(5 minutes)"
}

resource "aws_cloudwatch_event_rule" "poll" {
  name                = "${local.name}-poll-settlements"
  schedule_expression = var.poll_schedule
  tags                = local.tags
}

resource "aws_cloudwatch_event_target" "poll" {
  rule = aws_cloudwatch_event_rule.poll.name
  arn  = aws_lambda_function.app.arn
}

resource "aws_lambda_permission" "poll" {
  statement_id  = "AllowSettlementPoll"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.app.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.poll.arn
}
