"""Identity at ingress (E2A v1.7.4): with API Gateway's JWT authorizer, the API serves only callers
whose verified claims name this deployment's tenant. Through the real Lambda entry (Mangum)."""
import json

import pytest

from reconciliation_service import lambda_entry


def http_event(path, claims=None, method="GET"):
    context = {"http": {"method": method, "path": path, "sourceIp": "1.1.1.1", "protocol": "HTTP/1.1",
                        "userAgent": "t"}, "stage": "$default", "requestId": "r", "accountId": "1", "apiId": "a",
               "domainName": "x", "domainPrefix": "x", "time": "now", "timeEpoch": 0}
    if claims is not None:                                   # what the JWT authorizer adds (payload 2.0)
        context["authorizer"] = {"jwt": {"claims": claims, "scopes": None}}
    return {"version": "2.0", "routeKey": "$default", "rawPath": path, "rawQueryString": "",
            "headers": {"host": "x"}, "isBase64Encoded": False, "requestContext": context}


def cognito(tenant, *groups):
    return {"sub": "u-1", "iss": "https://cognito-idp.eu-west-1.amazonaws.com/pool", "custom:tenant_id": tenant,
            "cognito:groups": "[" + " ".join(groups) + "]"}


@pytest.fixture
def wired(service):
    """Point the module-level app at the moto-backed service for one test."""
    original = lambda_entry.app.state.recon_service
    lambda_entry.app.state.recon_service = service
    yield service
    lambda_entry.app.state.recon_service = original


@pytest.fixture
def identity_on(wired, monkeypatch):
    monkeypatch.setenv("E2A_IDENTITY_SOURCE", "aws_http_api")
    return wired


def status(event):
    return lambda_entry.handler(event, None)["statusCode"]


def test_a_caller_of_this_tenant_is_served(identity_on):
    response = lambda_entry.handler(http_event("/api/v1/exceptions", cognito("acme", "reconciler")), None)
    assert response["statusCode"] == 200 and json.loads(response["body"]) == []


def test_no_verified_claims_or_another_tenant_is_refused(identity_on):
    assert status(http_event("/api/v1/exceptions")) == 401
    assert status(http_event("/api/v1/exceptions", cognito("globex", "reconciler"))) == 403


def test_a_required_role_is_enforced(identity_on, monkeypatch):
    monkeypatch.setenv("RECON_REQUIRED_ROLE", "reconciler")
    assert status(http_event("/api/v1/exceptions", cognito("acme", "viewer"))) == 403
    assert status(http_event("/api/v1/exceptions", cognito("acme", "viewer", "reconciler"))) == 200


def test_health_stays_open_and_identity_is_off_without_a_source(wired, monkeypatch):
    monkeypatch.delenv("E2A_IDENTITY_SOURCE", raising=False)
    assert status(http_event("/health")) == 200
    assert status(http_event("/api/v1/exceptions")) == 200            # local and moto runs: off
