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

run "service_callers_have_their_own_route_and_authorizer" {
  command = plan
  variables {
    jwt_issuer           = "https://cognito-idp.eu-west-1.amazonaws.com/pool"
    jwt_audience         = ["client"]
    service_jwt_issuer   = "https://login.microsoftonline.com/dir/v2.0"
    service_jwt_audience = ["reconciliation-app"]
  }
  assert {
    condition     = aws_apigatewayv2_route.service_exceptions[0].route_key == "GET /service/v1/exceptions" && aws_apigatewayv2_route.service_exceptions[0].authorization_type == "JWT" && aws_apigatewayv2_route.service_lines[0].authorization_type == "JWT"
    error_message = "The service route requires a token"
  }
  assert {
    condition     = aws_apigatewayv2_authorizer.service[0].jwt_configuration[0].issuer == "https://login.microsoftonline.com/dir/v2.0" && aws_apigatewayv2_authorizer.jwt[0].jwt_configuration[0].issuer == "https://cognito-idp.eu-west-1.amazonaws.com/pool"
    error_message = "Services are verified against Entra, users against Cognito"
  }
  assert {
    condition     = aws_lambda_function.app.environment[0].variables["RECON_SERVICE_TRUSTED_ISSUERS"] == "[\"https://login.microsoftonline.com/dir/v2.0\"]"
    error_message = "The Lambda trusts only the landscape directory for service callers"
  }
}

run "no_unverified_service_route_when_users_are_verified" {
  command = plan
  variables {
    jwt_issuer   = "https://cognito-idp.eu-west-1.amazonaws.com/pool"
    jwt_audience = ["client"]
  }
  assert {
    condition     = length(aws_apigatewayv2_route.service_exceptions) == 0 && length(aws_apigatewayv2_route.service_lines) == 0
    error_message = "Without a service issuer, a deployment that verifies users must not expose an open service route"
  }
}

run "settlement_calls_carry_this_services_token" {
  command = plan
  variables {
    entra_directory_id         = "dir"
    entra_client_id            = "recon-app"
    settlement_scope           = "api://landscape-test-settlement/.default"
    setting_settlement_api_url = "https://settlement.example"
  }
  assert {
    condition     = aws_lambda_function.app.environment[0].variables["E2A_WORKLOAD_IDENTITY"] == "aws" && aws_lambda_function.app.environment[0].variables["E2A_WORKLOAD_TOKEN_SCOPES"] == "{\"https://settlement.example\":\"api://landscape-test-settlement/.default\"}"
    error_message = "The Lambda exchanges its STS web identity token for an Entra token for settlement-service"
  }
  assert {
    condition     = length(aws_iam_role_policy.workload) == 1
    error_message = "The role may call sts:GetWebIdentityToken"
  }
}
