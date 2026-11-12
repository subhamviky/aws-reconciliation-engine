# Copied next to main.tf ONLY by the CI job "terraform-apply-moto": points the AWS
# provider at a local moto server, so `terraform apply` really creates the stack
# without an AWS account. Never committed into infra/ itself.
provider "aws" {
  region                      = var.region
  access_key                  = "test"
  secret_key                  = "test"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true

  endpoints {
    apigatewayv2   = "http://localhost:5000"
    cloudwatchlogs = "http://localhost:5000"
    dynamodb       = "http://localhost:5000"
    eventbridge    = "http://localhost:5000"
    iam            = "http://localhost:5000"
    lambda         = "http://localhost:5000"
    secretsmanager = "http://localhost:5000"
    sqs            = "http://localhost:5000"
    sts            = "http://localhost:5000"
  }
}
