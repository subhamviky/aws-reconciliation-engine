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


ARN = "arn:aws:sqs:eu-west-1:123456789012:recon-lines"


def sqs_event(*bodies):
    return {"Records": [{"messageId": f"m{i}", "receiptHandle": f"r{i}", "eventSource": "aws:sqs",
                         "eventSourceARN": ARN, "body": b, "attributes": {"ApproximateReceiveCount": "1"}}
                        for i, b in enumerate(bodies)]}


@pytest.fixture
def queues(table, monkeypatch):
    """The bank-line queue and its DLQ, as infra/main.tf names them (moto, inside the table's mock)."""
    import boto3
    sqs = boto3.client("sqs", region_name="eu-west-1")
    url = sqs.create_queue(QueueName="recon-lines")["QueueUrl"]
    sqs.create_queue(QueueName="recon-lines-dlq")
    monkeypatch.setattr(lambda_entry, "_sqs", lambda: sqs)
    monkeypatch.setenv("QUEUE_URL", url)
    return sqs


def dead_letters(sqs):
    url = sqs.get_queue_url(QueueName="recon-lines-dlq")["QueueUrl"]
    return sqs.receive_message(QueueUrl=url, MaxNumberOfMessages=10, MessageAttributeNames=["All"]).get("Messages", [])


def test_an_sqs_batch_is_settled_by_the_consumer_and_poison_goes_to_the_dlq(wired, feed, queues):
    feed.completed("S1", "100.00")
    wired.poll_settlements()
    good = line("L1", "100.00").model_dump_json()
    result = lambda_entry.handler(sqs_event(good, "{not json", good), None)
    assert result == {"batchItemFailures": []}                 # nothing to redeliver: done or dead-lettered
    assert wired.repo.get_open_item(TENANT, ACCOUNT, sid("S1")).status == "MATCHED"
    [poison] = dead_letters(queues)
    assert poison["Body"] == '{"_raw":"{not json"}' and \
        "missing" in poison["MessageAttributes"]["dead_letter_reason"]["StringValue"]


def test_a_transient_failure_is_reported_for_redelivery(wired, feed, queues, monkeypatch):
    def down(line):
        raise ConnectionError("the repository is unavailable")
    monkeypatch.setattr(wired, "process_line", down)
    result = lambda_entry.handler(sqs_event(line("L9", "1.00").model_dump_json()), None)
    assert result == {"batchItemFailures": [{"itemIdentifier": "m0"}]} and dead_letters(queues) == []


def test_the_schedule_reconciles_the_dlq(wired, feed, queues):
    feed.completed("S1", "100.00")
    url = queues.get_queue_url(QueueName="recon-lines-dlq")["QueueUrl"]
    # a line dead-lettered before it took effect (its delivery's outcome was unknown)
    wired.claims.claim("L1", tenant_id=TENANT, owner="lost")
    wired.claims.fail("L1", retryable=False, tenant_id=TENANT, owner="lost", outcome="UNKNOWN")
    queues.send_message(QueueUrl=url, MessageBody=line("L1", "100.00").model_dump_json())
    result = lambda_entry.handler({"source": "aws.events", "detail-type": "Scheduled Event"}, None)
    assert result["dead_letters"] == {"status": "RECONCILED", "replayed": 1, "unresolved": []}
    assert wired.repo.get_open_item(TENANT, ACCOUNT, sid("S1")).status == "MATCHED"
    assert dead_letters(queues) == []                          # settled: removed from the DLQ


def test_schedule_polls_the_settlement_feed(wired, feed, monkeypatch):
    monkeypatch.delenv("QUEUE_URL", raising=False)            # no queue: nothing to reconcile
    feed.completed("S1", "100.00")
    assert lambda_entry.handler({"source": "aws.events", "detail-type": "Scheduled Event"}, None) == \
        {"ingested": 1, "ledger_posted": 0}


def test_http_goes_through_mangum(wired):
    event = {"version": "2.0", "routeKey": "$default", "rawPath": "/health", "rawQueryString": "",
             "headers": {"host": "x"}, "isBase64Encoded": False,
             "requestContext": {"http": {"method": "GET", "path": "/health", "sourceIp": "1.1.1.1",
                                         "protocol": "HTTP/1.1", "userAgent": "t"}, "stage": "$default",
                                "requestId": "r", "accountId": "1", "apiId": "a", "domainName": "x",
                                "domainPrefix": "x", "time": "now", "timeEpoch": 0}}
    response = lambda_entry.handler(event, None)
    assert response["statusCode"] == 200 and json.loads(response["body"])["status"] == "UP"
