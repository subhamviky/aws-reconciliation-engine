# Plans the configuration against a mocked AWS provider: no account and no
# credentials. Data sources return random strings unless given defaults.
mock_provider "aws" {
  mock_data "aws_iam_policy_document" {
    defaults = {
      json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
    }
  }
}

run "plan_with_mocks" {
  command = plan

  assert {
    condition     = contains(aws_lambda_event_source_mapping.queue.function_response_types, "ReportBatchItemFailures")
    error_message = "The queue consumer must report partial batch failures."
  }

  assert {
    condition     = aws_sqs_queue.dlq.message_retention_seconds == 1209600
    error_message = "The dead-letter queue must keep messages for 14 days."
  }

  assert {
    condition     = aws_dynamodb_table.recon.hash_key == "pk" && aws_dynamodb_table.recon.range_key == "sk"
    error_message = "The table must use the pk / sk keys the repository writes."
  }

  assert {
    condition     = aws_dynamodb_table.recon.ttl[0].enabled && aws_dynamodb_table.recon.ttl[0].attribute_name == "ttl"
    error_message = "TTL on \"ttl\" garbage-collects E2A's claims (e2a-adapters)."
  }

  assert {
    condition     = aws_dynamodb_table.recon.point_in_time_recovery[0].enabled
    error_message = "Reconciliation state must be recoverable (PITR)."
  }

  assert {
    condition     = aws_lambda_function.app.handler == "reconciliation_service.lambda_entry.handler"
    error_message = "The Lambda must run the service's entry point."
  }

  assert {
    condition     = aws_lambda_function.app.environment[0].variables["RECON_TENANT"] == "acme"
    error_message = "The Lambda must know its tenant."
  }

  assert {
    condition     = aws_cloudwatch_event_rule.poll.schedule_expression == "rate(5 minutes)"
    error_message = "The settlement feed must be polled on a schedule."
  }

  assert {
    condition     = contains(keys(aws_lambda_function.app.environment[0].variables), "TABLE_NAME")
    error_message = "The setting TABLE_NAME must reach the runtime."
  }

  assert {
    condition     = contains(keys(aws_lambda_function.app.environment[0].variables), "SETTLEMENT_API_URL")
    error_message = "The setting SETTLEMENT_API_URL must reach the runtime."
  }

  assert {
    condition     = contains(keys(aws_lambda_function.app.environment[0].variables), "RECON_TENANT")
    error_message = "The setting RECON_TENANT must reach the runtime."
  }
}

run "identity_at_ingress" {
  command = plan

  variables {
    jwt_issuer    = "https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_example"
    jwt_audience  = ["example-client-id"]
    required_role = "reconciler"
  }

  assert {
    condition     = aws_apigatewayv2_authorizer.jwt[0].authorizer_type == "JWT" && aws_apigatewayv2_route.proxy.authorization_type == "JWT"
    error_message = "With an issuer, API Gateway verifies every caller's token."
  }

  assert {
    condition     = aws_lambda_function.app.environment[0].variables["E2A_IDENTITY_SOURCE"] == "aws_http_api" && aws_lambda_function.app.environment[0].variables["RECON_REQUIRED_ROLE"] == "reconciler"
    error_message = "The Lambda takes the caller from the verified claims."
  }

  assert {
    condition     = aws_apigatewayv2_route.health.authorization_type == "NONE"
    error_message = "The liveness probe needs no token."
  }
}

run "identity_off_without_an_issuer" {
  command = plan

  assert {
    condition     = length(aws_apigatewayv2_authorizer.jwt) == 0 && !contains(keys(aws_lambda_function.app.environment[0].variables), "E2A_IDENTITY_SOURCE")
    error_message = "Without an issuer (local and moto runs) identity at ingress is off."
  }
}
