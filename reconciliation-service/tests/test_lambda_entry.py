"""The single Lambda handler: SQS batches, the EventBridge schedule and HTTP."""
import json

import pytest

from conftest import sid, ACCOUNT, TENANT, line
from reconciliation_service import lambda_entry


@pytest.fixture
def wired(service):
    """Point the module-level app at the moto-backed service for one test."""
    original = lambda_entry.app.state.recon_service
    lambda_entry.app.state.recon_service = service
    yield service
    lambda_entry.app.state.recon_service = original


def sqs_event(*bodies):
    return {"Records": [{"messageId": f"m{i}", "eventSource": "aws:sqs", "body": b}
                        for i, b in enumerate(bodies)]}


def test_sqs_batch_reports_only_the_poison_message(wired, feed):
    feed.completed("S1", "100.00")
    wired.poll_settlements()
    result = lambda_entry.handler(sqs_event(line("L1", "100.00").model_dump_json(), "{not json"), None)
    assert result == {"batchItemFailures": [{"itemIdentifier": "m1"}]}
    assert wired.repo.get_open_item(TENANT, ACCOUNT, sid("S1")).status == "MATCHED"


def test_schedule_polls_the_settlement_feed(wired, feed):
    feed.completed("S1", "100.00")
    assert lambda_entry.handler({"source": "aws.events", "detail-type": "Scheduled Event"}, None) == {"ingested": 1}


def test_http_goes_through_mangum(wired):
    event = {"version": "2.0", "routeKey": "$default", "rawPath": "/health", "rawQueryString": "",
             "headers": {"host": "x"}, "isBase64Encoded": False,
             "requestContext": {"http": {"method": "GET", "path": "/health", "sourceIp": "1.1.1.1",
                                         "protocol": "HTTP/1.1", "userAgent": "t"}, "stage": "$default",
                                "requestId": "r", "accountId": "1", "apiId": "a", "domainName": "x",
                                "domainPrefix": "x", "time": "now", "timeEpoch": 0}}
    response = lambda_entry.handler(event, None)
    assert response["statusCode"] == 200 and json.loads(response["body"])["status"] == "UP"
