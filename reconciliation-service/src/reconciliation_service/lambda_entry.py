"""The one Lambda handler infra/main.tf points at (var.lambda_handler):

  SQS batch          -> E2A's IdempotentConsumer settles each bank line (SQSLambdaBatch, E2A v1.7.2):
                        a transient failure is reported (ReportBatchItemFailures) and
                        redelivered; a line that can never succeed goes to the DLQ at once,
                        with the reason; the redrive policy (maxReceiveCount) still caps retries
  EventBridge rule   -> poll the settlement feed, retry pending ledger postings (schedule.tf), and
                        reconcile the DLQ: each dead letter is confirmed against the repository
                        and replayed only if it never took effect
  API Gateway (HTTP) -> the FastAPI app through Mangum
"""
import logging
import os
from typing import Any, Dict

from mangum import Mangum

from .main import app
from .services.line_consumer import BankLineConsumer
from .services.recon_service import CONSUMER_CONFIG

logger = logging.getLogger("reconciliation_service")
_http = Mangum(app, lifespan="off")


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    service = app.state.recon_service
    if "Records" in event and event["Records"] and event["Records"][0].get("eventSource") == "aws:sqs":
        from e2a_adapters.aws import SQSLambdaBatch
        batch = SQSLambdaBatch(event, _sqs())
        report = BankLineConsumer(service, batch).consume(batch.source, CONSUMER_CONFIG)
        for settled in report["messages"]:                    # one bad message never fails the batch
            if settled["decision"] in ("retried", "dead_lettered"):
                logger.warning("bank line %s %s: %s", settled["idempotency_key"] or settled["message_id"],
                               settled["decision"], settled["reason"])
        return batch.batch_item_failures()
    if event.get("source") == "aws.events":
        result = {"ingested": service.poll_settlements(), "ledger_posted": service.retry_ledger_postings()}
        queue = _queue_name()
        if queue:                                             # the DLQ, under a lease (one run at a time)
            from e2a_adapters.aws import SQSBroker
            reconciled = BankLineConsumer(service, SQSBroker(_sqs()), queue, lock=service.lease) \
                .reconcile(CONSUMER_CONFIG, dlq_source=queue)
            result["dead_letters"] = {k: reconciled.get(k) for k in ("status", "replayed", "unresolved")}
        return result
    return _http(event, context)


def _sqs():
    import boto3
    return boto3.client("sqs")


def _queue_name() -> str:
    """The bank-line queue (QUEUE_URL from infra/main.tf); its DLQ is <queue>-dlq."""
    return os.getenv("QUEUE_URL", "").rstrip("/").rsplit("/", 1)[-1]
