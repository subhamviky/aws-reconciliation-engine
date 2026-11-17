# Service-to-service identity (hub design note SI-01).
#
# Inbound: o2c-agent-service reads open exceptions on GET /service/v1/exceptions with an Entra
# access token for the reconciliation app. A second JWT authorizer (issuer: the landscape's Entra
# directory) verifies it; the users' authorizer (Cognito) keeps every other route. The service
# requires the tenant and reconciliation.read as app roles (routers/identity.py).
#
# Outbound: calls to settlement-service carry this service's own token. The Lambda's IAM role gets
# a web identity token from STS (IAM outbound identity federation) and exchanges it for an Entra
# token for the settlement app (e2a_adapters.workload). Enable the federation once per account:
#   aws iam enable-outbound-web-identity-federation
#   aws iam get-outbound-web-identity-federation-info     # the issuer, for landscape-identity
# landscape-identity/ (financial-settlement-platform) holds the apps, roles and grants.

variable "service_jwt_issuer" {
  type        = string
  description = "The landscape directory's v2 issuer (landscape-identity's output issuer). Empty: no service route outside local runs."
  default     = ""
}

variable "service_jwt_audience" {
  type        = list(string)
  description = "The reconciliation app's client id (landscape-identity's output reconciliation_audience)."
  default     = []
}

variable "entra_directory_id" {
  type        = string
  description = "The Entra directory that issues the landscape's workload tokens. Empty: calls to settlement-service carry no token."
  default     = ""
}

variable "entra_client_id" {
  type        = string
  description = "This service's caller app (landscape-identity's output recon_client_id)."
  default     = ""
}

variable "settlement_scope" {
  type        = string
  description = "The settlement app's scope (landscape-identity's output settlement_scope)."
  default     = ""
}

locals {
  service_identity_on = var.service_jwt_issuer != ""
  # a service route exists where its token is verified, or where nothing is (local and moto runs)
  service_route_on = local.service_identity_on || !local.identity_on
  workload_on      = var.entra_directory_id != "" && var.entra_client_id != "" && var.settlement_scope != ""
  workload_env = merge(
    local.service_identity_on ? {
      E2A_IDENTITY_SOURCE           = "aws_http_api"
      RECON_SERVICE_TRUSTED_ISSUERS = jsonencode([var.service_jwt_issuer])
    } : {},
    local.workload_on ? {
      E2A_WORKLOAD_IDENTITY        = "aws"
      E2A_WORKLOAD_AWS_REGION      = var.region
      E2A_WORKLOAD_ENTRA_TENANT    = var.entra_directory_id
      E2A_WORKLOAD_ENTRA_CLIENT_ID = var.entra_client_id
      E2A_WORKLOAD_TOKEN_SCOPES    = jsonencode({ (var.setting_settlement_api_url) = var.settlement_scope })
  } : {})
}

resource "aws_apigatewayv2_authorizer" "service" {
  count            = local.service_identity_on ? 1 : 0
  api_id           = aws_apigatewayv2_api.http.id
  name             = "${local.name}-service-jwt"
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]
  jwt_configuration {
    issuer   = var.service_jwt_issuer
    audience = var.service_jwt_audience
  }
}

resource "aws_apigatewayv2_route" "service_exceptions" {
  count              = local.service_route_on ? 1 : 0
  api_id             = aws_apigatewayv2_api.http.id
  route_key          = "GET /service/v1/exceptions"
  target             = "integrations/${aws_apigatewayv2_integration.app.id}"
  authorization_type = local.service_identity_on ? "JWT" : "NONE"
  authorizer_id      = local.service_identity_on ? aws_apigatewayv2_authorizer.service[0].id : null
}

data "aws_iam_policy_document" "workload" {
  statement {
    sid       = "OwnWebIdentityToken"
    actions   = ["sts:GetWebIdentityToken"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "workload" {
  count  = local.workload_on ? 1 : 0
  name   = "${local.name}-workload-identity"
  role   = aws_iam_role.app.id
  policy = data.aws_iam_policy_document.workload.json
}
