# Expected cash: an EventBridge schedule invokes the same Lambda, which polls the
# settlement-service event feed from its durable cursor (lambda_entry.handler,
# branch source == "aws.events").

# SETTLEMENT_API_URL and RECON_TENANT are app settings declared in the A2C request (main.tf).

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
