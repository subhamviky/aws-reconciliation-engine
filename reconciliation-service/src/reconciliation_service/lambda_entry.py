"""The one Lambda handler infra/main.tf points at (var.lambda_handler):

  SQS batch          -> reconcile each bank line; failed records are reported
                        individually (ReportBatchItemFailures) and reach the DLQ
                        after maxReceiveCount
  EventBridge rule   -> poll the settlement feed (schedule.tf)
  API Gateway (HTTP) -> the FastAPI app through Mangum
"""
import logging
from typing import Any, Dict

from mangum import Mangum

from .main import app
from .models.records import BankLine

logger = logging.getLogger("reconciliation_service")
_http = Mangum(app, lifespan="off")


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    service = app.state.recon_service
    if "Records" in event and event["Records"] and event["Records"][0].get("eventSource") == "aws:sqs":
        failures = []
        for record in event["Records"]:
            try:
                service.reconcile(BankLine.model_validate_json(record["body"]))
            except Exception:                                  # one bad message never fails the batch
                logger.exception("bank line %s failed", record.get("messageId"))
                failures.append({"itemIdentifier": record["messageId"]})
        return {"batchItemFailures": failures}
    if event.get("source") == "aws.events":
        return {"ingested": service.poll_settlements()}
    return _http(event, context)
