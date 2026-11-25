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

Service callers (hub design note SI-01) use /service/v1/...: API Gateway verifies their Entra
access token with a second authorizer (infra/identity.tf, service_jwt_issuer), and
require_service_identity() resolves it as a service: X-Tenant-Id must be this deployment's
tenant and granted to the caller (app role tenant:<id>), and the route's action role must be
granted (reconciliation.read).
  RECON_SERVICE_TRUSTED_ISSUERS  JSON list: the landscape directory's v2 issuer (infra sets it)

Google Cloud, free tier (GCP-01, E2A v1.11.0): with E2A_IDENTITY_SOURCE=gcp_cloud_run, Cloud Run
IAM has verified the caller's Google ID token (people and services alike) and the service reads it
from the request headers. The token names only an email, so every caller is resolved the way
services are: the deployment grants it this tenant ("tenant:<id>") and its roles in
E2A_IDENTITY_SUBJECT_ROLES (trusted issuer https://accounts.google.com, E2A_IDENTITY_TRUSTED_ISSUERS).
"""
import json
import os

from e2a import IdentityRefused, require_roles
from fastapi import HTTPException, Request


CLOUD_RUN = "gcp_cloud_run"


def _cloud_run_config() -> dict:
    """Users and services alike: the Google ID token's email, granted tenant and roles by configuration."""
    from e2a_adapters.identity import preset
    return {"identity_source": CLOUD_RUN, "identity_claim_map": preset("google_id_token"),
            "identity_tenants_from_roles": "tenant:"}


def _config() -> dict:
    from e2a_adapters.identity import preset
    if os.getenv("E2A_IDENTITY_SOURCE") == CLOUD_RUN:
        return _cloud_run_config()
    return {"identity_source": os.getenv("E2A_IDENTITY_SOURCE") or None,
            **({} if os.getenv("E2A_IDENTITY_CLAIM_MAP") else {"identity_claim_map": preset("cognito")})}


def require_identity(request: Request) -> None:
    from e2a_adapters.ingress import identity_at_ingress
    tenant = request.app.state.recon_service.tenant
    try:
        identity = identity_at_ingress(_config(), event=request.scope.get("aws.event"), headers=request.headers,
                                       request_tenant=tenant)
    except IdentityRefused as refused:
        raise HTTPException(status_code=401 if "not verified" in str(refused) else 403, detail=str(refused))
    except ValueError as malformed:
        raise HTTPException(status_code=401, detail=str(malformed))
    required = os.getenv("RECON_REQUIRED_ROLE")
    if identity is not None and required and required not in identity.roles:
        raise HTTPException(status_code=403, detail=f"the credentials do not carry the role {required!r}")
    request.state.identity = identity


def _service_config() -> dict:
    from e2a_adapters.identity import preset
    if os.getenv("E2A_IDENTITY_SOURCE") == CLOUD_RUN:
        return _cloud_run_config()
    return {"identity_source": os.getenv("E2A_IDENTITY_SOURCE") or None,
            "identity_claim_map": preset("entra_service"), "identity_tenants_from_roles": "tenant:",
            "identity_trusted_issuers": json.loads(os.getenv("RECON_SERVICE_TRUSTED_ISSUERS") or "[]")}


def service_identity(*roles: str):
    """A dependency: the calling service, granted this deployment's tenant and `roles`."""
    def require_service_identity(request: Request) -> None:
        from e2a_adapters.ingress import identity_at_ingress
        tenant = request.app.state.recon_service.tenant
        named = request.headers.get("X-Tenant-Id")
        try:
            if named is not None and named != tenant:
                raise IdentityRefused(f"this deployment serves tenant {tenant!r}", "identity")
            identity = identity_at_ingress(_service_config(), event=request.scope.get("aws.event"), headers=request.headers,
                                           request_tenant=named or tenant)
            if identity is not None:
                require_roles(identity, *roles)
        except IdentityRefused as refused:
            raise HTTPException(status_code=401 if "not verified" in str(refused) else 403, detail=str(refused))
        except ValueError as malformed:
            raise HTTPException(status_code=401, detail=str(malformed))
        request.state.identity = identity
    return require_service_identity
