"""Who may call the API: identity at ingress (E2A v1.7.4, hub design note MP-05, N3).

In AWS, API Gateway's JWT authorizer (infra/main.tf, when jwt_issuer is set) verifies the
caller's Cognito token; the verified claims reach the Lambda in the event
(requestContext.authorizer.jwt.claims), Mangum keeps the event in the request scope, and
e2a-adapters reads them for E2A's ClaimMapIdentityResolver. Configured by environment:

  E2A_IDENTITY_SOURCE          aws_http_api (infra sets it with the authorizer); unset = off
  E2A_IDENTITY_CLAIM_MAP       JSON claim map (default: the Cognito preset,
                               tenant = custom:tenant_id, roles = cognito:groups)
  E2A_IDENTITY_TRUSTED_ISSUERS JSON list of accepted issuers (optional)
  RECON_REQUIRED_ROLE          a role every caller must carry (optional)

This deployment serves one tenant (RECON_TENANT): the claims must name it. Fail-closed when
configured: no verified claims 401; another tenant or a missing role 403.
"""
import os

from e2a import IdentityRefused
from fastapi import HTTPException, Request


def _config() -> dict:
    from e2a_adapters.identity import preset
    return {"identity_source": os.getenv("E2A_IDENTITY_SOURCE") or None,
            **({} if os.getenv("E2A_IDENTITY_CLAIM_MAP") else {"identity_claim_map": preset("cognito")})}


def require_identity(request: Request) -> None:
    from e2a_adapters.ingress import identity_at_ingress
    tenant = request.app.state.recon_service.tenant
    try:
        identity = identity_at_ingress(_config(), event=request.scope.get("aws.event"), request_tenant=tenant)
    except IdentityRefused as refused:
        raise HTTPException(status_code=401 if "not verified" in str(refused) else 403, detail=str(refused))
    except ValueError as malformed:
        raise HTTPException(status_code=401, detail=str(malformed))
    required = os.getenv("RECON_REQUIRED_ROLE")
    if identity is not None and required and required not in identity.roles:
        raise HTTPException(status_code=403, detail=f"the credentials do not carry the role {required!r}")
    request.state.identity = identity
