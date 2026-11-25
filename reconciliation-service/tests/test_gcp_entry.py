"""Google Cloud entry points (GCP-01): a Pub/Sub push of a bank line settled by E2A's
IdempotentConsumer (PubSubPushDelivery, E2A v1.10.0), and the Cloud Scheduler job."""
import base64
import json

import pytest
from fastapi.testclient import TestClient

from conftest import ACCOUNT, line
from reconciliation_service.main import build_app


class _Future:
    def __init__(self, value):
        self.value = value

    def result(self, timeout=None):
        return self.value


class FakePublisher:
    def __init__(self):
        self.published = []

    def publish(self, topic, data, **attributes):
        self.published.append((topic, json.loads(data), attributes))
        return _Future("id")


@pytest.fixture
def gcp(service):
    from e2a_adapters.gcp import PubSubBroker
    app = build_app(service)
    publisher = FakePublisher()
    app.state.pubsub_broker = PubSubBroker("demo-project", publisher=publisher)
    return TestClient(app), publisher, service


def push(body, mid="m1", attempt=1):
    data = base64.b64encode((body if isinstance(body, str) else json.dumps(body)).encode()).decode()
    return {"message": {"data": data, "messageId": mid, "attributes": {}},
            "subscription": "projects/demo-project/subscriptions/recon-bank-lines", "deliveryAttempt": attempt}


def test_a_pushed_line_is_reconciled_once_and_answered_204(gcp, feed):
    client, _, service = gcp
    feed.completed("S1", "125.00")
    service.poll_settlements()
    body = json.loads(line("L1", "125.00", reference="S1").model_dump_json())
    assert client.post("/pubsub/bank-lines", json=push(body)).status_code == 204
    assert service.outcome_of("L1")["status"] == "MATCHED"
    again = client.post("/pubsub/bank-lines", json=push(body, mid="m2", attempt=2))   # Pub/Sub redelivers
    assert again.status_code == 204 and service.outcome_of("L1")["status"] == "MATCHED"


def test_a_poison_line_goes_to_the_dead_letter_topic_with_its_reason(gcp):
    client, publisher, _ = gcp
    assert client.post("/pubsub/bank-lines", json=push({"line_id": "L9", "amount": "x"})).status_code == 204
    topic, body, attrs = publisher.published[-1]
    assert topic == "projects/demo-project/topics/recon-bank-lines-dlq" and body["line_id"] == "L9"
    assert attrs["dead_letter_reason"]


def test_a_request_that_is_not_a_push_envelope_is_refused(gcp):
    client, _, _ = gcp
    assert client.post("/pubsub/bank-lines", json={"line_id": "L1"}).status_code == 400


def test_without_pubsub_configured_the_push_endpoint_says_so(service):
    app = build_app(service)
    app.state.pubsub_broker = None
    assert TestClient(app).post("/pubsub/bank-lines", json=push({"line_id": "L1"})).status_code == 503


def test_the_scheduled_job_polls_the_feed_and_retries_ledger_postings(gcp, feed):
    client, _, service = gcp
    feed.completed("S2", "40.00")
    result = client.post("/jobs/scheduled").json()
    assert result["ingested"] == 1 and result["ledger_posted"] == 0 and "dead_letters" not in result
    assert service.repo.get_open_item("acme", ACCOUNT, __import__("conftest").sid("S2")) is not None


def test_accepted_lines_are_published_to_pubsub_when_a_topic_is_set(service, monkeypatch):
    from reconciliation_service.services.queue import PubSubLineQueue
    publisher = FakePublisher()
    from e2a_adapters.gcp import PubSubBroker
    queue = PubSubLineQueue(PubSubBroker("demo-project", publisher=publisher), "recon-bank-lines")
    assert queue.submit([line("L5", "10.00")]) == [{"line_id": "L5", "status": "QUEUED"}]
    topic, body, attrs = publisher.published[-1]
    assert topic == "projects/demo-project/topics/recon-bank-lines" and body["line_id"] == "L5" and attrs == {"line_id": "L5"}
