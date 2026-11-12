"""Shared fixtures: a moto DynamoDB table shaped like infra/dynamodb.tf, and a fake
settlement feed that serves events in the settlement-service wire format."""
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List

import boto3
import pytest
from moto import mock_aws

from reconciliation_service.models.records import BankLine
from reconciliation_service.services.llm import build_triage_llm
from reconciliation_service.services.recon_service import ReconciliationService
from reconciliation_service.services.repository import ReconRepository

TENANT = "acme"
ACCOUNT = "ACC-PAYEE-1"
T0 = datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def aws_env(monkeypatch):
    for key, value in {"AWS_ACCESS_KEY_ID": "testing", "AWS_SECRET_ACCESS_KEY": "testing",
                       "AWS_DEFAULT_REGION": "eu-west-1"}.items():
        monkeypatch.setenv(key, value)


@pytest.fixture
def table():
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="eu-west-1")
        yield dynamodb.create_table(
            TableName="reconciliation", BillingMode="PAY_PER_REQUEST",
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}],
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"},
                                  {"AttributeName": "sk", "AttributeType": "S"}])


def sid(name: str) -> str:
    """Settlement ids are UUIDs (settlement-event.v1); tests name them S1, S2, ..."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"settlement/{name}"))


class FakeFeed:
    def __init__(self) -> None:
        self.events: List[Dict] = []

    def completed(self, name: str, amount: str, minutes: int = 0, account: str = ACCOUNT) -> None:
        """Append a settlement.completed event in the producer's wire format."""
        self.events.append({
            "event_id": str(uuid.uuid4()), "event_type": "settlement.completed", "schema_version": "1",
            "occurred_at": (T0 + timedelta(minutes=minutes)).isoformat(), "tenant_id": TENANT,
            "correlation_id": str(uuid.uuid4()),
            "settlement": {"settlement_id": sid(name), "payer_account": "ACC-PAYER-9",
                           "payee_account": account, "amount": amount, "currency": "EUR",
                           "status": "COMPLETED", "reason": None}})

    def events_after(self, tenant_id: str, after_sequence: int) -> Dict:
        page = [{"sequence": i + 1, "event": e} for i, e in enumerate(self.events) if i + 1 > after_sequence]
        return {"events": page, "next_after_sequence": page[-1]["sequence"] if page else after_sequence}


@pytest.fixture
def feed():
    return FakeFeed()


@pytest.fixture
def service(table, feed):
    return ReconciliationService(ReconRepository(table), feed, build_triage_llm(), TENANT)


def line(line_id: str, amount: str, reference: str = None, txn: str = None, day: int = 3,
         account: str = ACCOUNT) -> BankLine:
    return BankLine(line_id=line_id, bank_txn_id=txn or f"TXN-{line_id}", value_date=date(2026, 11, day),
                    amount=Decimal(amount), currency="EUR", counterparty_account=account, reference=reference)
