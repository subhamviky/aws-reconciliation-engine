"""Hub design note SI-01: service callers on /service/v1 (an Entra token, verified by its own
authorizer) and this service's own token on calls to settlement-service."""
import json

import httpx
import pytest

from reconciliation_service import lambda_entry
from reconciliation_service.services.ledger_client import HttpSettlementLedger
from reconciliation_service.services.settlement_client import HttpSettlementFeed

ISSUER = "https://login.microsoftonline.com/dir/v2.0"


def http_event(path, claims=None, tenant=None):
    context = {"http": {"method": "GET", "path": path, "sourceIp": "1.1.1.1", "protocol": "HTTP/1.1",
                        "userAgent": "t"}, "stage": "$default", "requestId": "r", "accountId": "1", "apiId": "a",
               "domainName": "x", "domainPrefix": "x", "time": "now", "timeEpoch": 0}
    if claims is not None:
        context["authorizer"] = {"jwt": {"claims": claims, "scopes": None}}
    headers = {"host": "x", **({"x-tenant-id": tenant} if tenant else {})}
    return {"version": "2.0", "routeKey": "$default", "rawPath": path, "rawQueryString": "",
            "headers": headers, "isBase64Encoded": False, "requestContext": context}


def service(*roles, iss=ISSUER):
    # an Entra v2 access token's claims as API Gateway hands them over (a list arrives as "[a b]")
    return {"iss": iss, "azp": "o2c-app", "tid": "dir", "roles": "[" + " ".join(roles) + "]"}


@pytest.fixture
def services_on(service_fixture, monkeypatch):
    monkeypatch.setenv("E2A_IDENTITY_SOURCE", "aws_http_api")
    monkeypatch.setenv("RECON_SERVICE_TRUSTED_ISSUERS", json.dumps([ISSUER]))
    return service_fixture


@pytest.fixture
def service_fixture(service):
    original = lambda_entry.app.state.recon_service
    lambda_entry.app.state.recon_service = service
    yield service
    lambda_entry.app.state.recon_service = original


def status(event):
    return lambda_entry.handler(event, None)["statusCode"]


def test_a_granted_service_reads_open_exceptions(services_on):
    response = lambda_entry.handler(http_event("/service/v1/exceptions", service("reconciliation.read", "tenant:acme"),
                                               tenant="acme"), None)
    assert response["statusCode"] == 200 and json.loads(response["body"]) == []


def test_a_granted_service_reads_one_bank_line(services_on):
    from decimal import Decimal
    from datetime import date
    from reconciliation_service.models.records import BankLine
    services_on.repo.add_line(services_on.tenant, BankLine(
        line_id="L-77", bank_txn_id="T-77", value_date=date(2026, 11, 2), amount=Decimal("357.50"), currency="EUR",
        counterparty_account="ACC-3000", reference=None))
    ok = lambda_entry.handler(http_event("/service/v1/lines/L-77", service("reconciliation.read", "tenant:acme"),
                                         tenant="acme"), None)
    assert ok["statusCode"] == 200 and json.loads(ok["body"])["amount"] == "357.50"
    missing = lambda_entry.handler(http_event("/service/v1/lines/NOPE", service("reconciliation.read", "tenant:acme"),
                                              tenant="acme"), None)
    assert missing["statusCode"] == 404
    assert status(http_event("/service/v1/lines/L-77", service("tenant:acme"), "acme")) == 403     # no read role
    assert status(http_event("/service/v1/lines/L-77", tenant="acme")) == 401                       # no claims


def test_without_claims_401_and_without_grants_403(services_on):
    assert status(http_event("/service/v1/exceptions", tenant="acme")) == 401
    assert status(http_event("/service/v1/exceptions", service("reconciliation.read", "tenant:globex"), "acme")) == 403
    assert status(http_event("/service/v1/exceptions", service("tenant:acme"), "acme")) == 403
    assert status(http_event("/service/v1/exceptions", service("reconciliation.read", "tenant:acme"), "globex")) == 403


def test_only_the_landscape_directory_is_trusted_for_services(services_on):
    other = service("reconciliation.read", "tenant:acme", iss="https://cognito-idp.eu-west-1.amazonaws.com/pool")
    assert status(http_event("/service/v1/exceptions", other, "acme")) == 403


def test_a_service_token_is_not_a_user_token(services_on):
    # the users' routes keep the Cognito claim map: a service's claims name no tenant there
    assert status(http_event("/api/v1/exceptions", service("reconciliation.read", "tenant:acme"), "acme")) == 403


def test_off_without_a_source(service_fixture, monkeypatch):
    monkeypatch.delenv("E2A_IDENTITY_SOURCE", raising=False)
    assert status(http_event("/service/v1/exceptions", tenant="acme")) == 200


class Credentials:
    def __init__(self):
        self.targets = []

    def headers(self, target, scope=None, config=None, **kwargs):
        self.targets.append(target)
        return {"Authorization": "Bearer recon-token"}


def test_calls_to_settlement_service_carry_this_services_token():
    seen, creds = [], Credentials()

    def handle(request):
        seen.append(dict(request.headers))
        if request.url.path.endswith("/events"):
            return httpx.Response(200, json={"events": [], "next_after_sequence": 0})
        return httpx.Response(201, json={"adjustmentId": "a-1", "type": "WRITE_OFF", "amount": "1.00"})

    transport = httpx.MockTransport(handle)
    HttpSettlementFeed("https://settlement.example", credentials=creds, transport=transport).events_after("acme", 0)
    HttpSettlementLedger("https://settlement.example", transport=transport, credentials=creds).post_adjustment(
        "acme", {"settlement_id": "s-1", "type": "WRITE_OFF", "amount": "1.00", "reason": "r", "reference": "l-1",
                 "key": "k-1"})
    assert [h["authorization"] for h in seen] == ["Bearer recon-token"] * 2
    assert creds.targets == ["https://settlement.example/api/v1/events",
                             "https://settlement.example/api/v1/settlements/s-1/adjustments"]


def test_without_credentials_no_authorization_header():
    seen = []
    transport = httpx.MockTransport(lambda r: seen.append(dict(r.headers)) or httpx.Response(
        200, json={"events": [], "next_after_sequence": 0}))
    HttpSettlementFeed("https://settlement.example", transport=transport).events_after("acme", 0)
    assert "authorization" not in seen[0]
