"""Where accepted bank lines go: SQS in AWS (the Lambda consumes the queue, with the
dead-letter queue from infra/main.tf), or straight to the service locally and in tests."""
from typing import Callable, Dict, List

from ..models.records import BankLine


class SqsLineQueue:
    mode = "sqs"

    def __init__(self, sqs_client, queue_url: str) -> None:
        self.sqs, self.queue_url = sqs_client, queue_url

    def submit(self, lines: List[BankLine]) -> List[Dict]:
        for line in lines:
            self.sqs.send_message(QueueUrl=self.queue_url, MessageBody=line.model_dump_json())
        return [{"line_id": l.line_id, "status": "QUEUED"} for l in lines]


class DirectLineQueue:
    mode = "direct"

    def __init__(self, handle: Callable[[BankLine], Dict]) -> None:
        self.handle = handle

    def submit(self, lines: List[BankLine]) -> List[Dict]:
        from .recon_service import LineConflict, LineInProgress
        results = []
        for line in lines:
            try:
                results.append(self.handle(line))
            except LineInProgress:              # SQS would redeliver; synchronously the caller retries
                results.append({"line_id": line.line_id, "status": "IN_PROGRESS"})
            except LineConflict as e:
                results.append({"line_id": line.line_id, "status": "CONFLICT", "detail": str(e)})
        return results


class PubSubLineQueue:
    """Google Cloud (GCP-01): accepted lines are published to a Pub/Sub topic; a push subscription
    delivers each to POST /pubsub/bank-lines, where E2A's IdempotentConsumer settles it under the
    same claim as every other path (PubSubPushDelivery, E2A v1.10.0)."""
    mode = "pubsub"

    def __init__(self, broker, topic: str) -> None:
        self.broker, self.topic = broker, topic

    def submit(self, lines: List[BankLine]) -> List[Dict]:
        import json
        for line in lines:
            self.broker.publish(self.topic, json.loads(line.model_dump_json()), {"line_id": line.line_id})
        return [{"line_id": l.line_id, "status": "QUEUED"} for l in lines]
