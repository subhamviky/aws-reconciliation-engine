# Identity at ingress (E2A v1.7.4): with jwt_issuer set (a Cognito user pool, for example),
# API Gateway's JWT authorizer verifies every caller's token, every API route requires it, and
# the Lambda takes the caller from the verified claims (E2A_IDENTITY_SOURCE=aws_http_api): the
# claims must name this deployment's tenant (RECON_TENANT). /health stays open. Without
# jwt_issuer the API is unauthenticated, as before: for local and moto runs only.

variable "jwt_issuer" {
  type        = string
  description = "Token issuer, e.g. https://cognito-idp.<region>.amazonaws.com/<user-pool-id>. Required in production."
  default     = ""
}

variable "jwt_audience" {
  type        = list(string)
  description = "Accepted audiences (for Cognito access tokens, the app client id; API Gateway checks client_id when aud is absent)."
  default     = []
}

variable "required_role" {
  type        = string
  description = "A role (Cognito group) every caller must carry; empty: any authenticated user of the tenant."
  default     = ""
}

locals {
  identity_on = var.jwt_issuer != ""
  identity_env = local.identity_on ? {
    E2A_IDENTITY_SOURCE          = "aws_http_api"
    E2A_IDENTITY_TRUSTED_ISSUERS = jsonencode([var.jwt_issuer])
    RECON_REQUIRED_ROLE          = var.required_role
  } : {}
}

resource "aws_apigatewayv2_authorizer" "jwt" {
  count            = local.identity_on ? 1 : 0
  api_id           = aws_apigatewayv2_api.http.id
  name             = "${local.name}-jwt"
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]
  jwt_configuration {
    issuer   = var.jwt_issuer
    audience = var.jwt_audience
  }
}

# The liveness probe needs no token.
resource "aws_apigatewayv2_route" "health" {
  api_id             = aws_apigatewayv2_api.http.id
  route_key          = "GET /health"
  target             = "integrations/${aws_apigatewayv2_integration.app.id}"
  authorization_type = "NONE"
}
