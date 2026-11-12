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
}
