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
        return [self.handle(line) for line in lines]
