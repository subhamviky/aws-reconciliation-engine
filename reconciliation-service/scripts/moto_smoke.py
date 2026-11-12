"""Smoke test of the stack `terraform apply` created on the moto server.

Uses the real table and queue from the Terraform outputs (TABLE_NAME, QUEUE_URL;
AWS_ENDPOINT_URL points boto3 at moto): a settlement event becomes an open item,
a bank line goes onto the SQS queue, the Lambda handler consumes the batch exactly
as the event source mapping would deliver it, and the line ends up MATCHED.
Run by CI job terraform-apply-moto:  poetry run python scripts/moto_smoke.py
"""
import json
import os
import sys

import boto3

from reconciliation_service import lambda_entry
from reconciliation_service.models.records import BankLine


class OneEventFeed:
    def events_after(self, tenant_id, after_sequence):
        event = {"event_id": "6f1c0b52-6c55-4a4e-9a7e-2f1b7d1c9a01", "event_type": "settlement.completed", "schema_version": "1",
                 "occurred_at": "2026-11-02T09:00:00+00:00", "tenant_id": tenant_id, "correlation_id": "6f1c0b52-6c55-4a4e-9a7e-2f1b7d1c9a02",
                 "settlement": {"settlement_id": "aa4b83bf-e397-5857-96f6-6150b6914177", "payer_account": "ACC-PAYER-9",
                                "payee_account": "ACC-PAYEE-1", "amount": "100.00", "currency": "EUR",
                                "status": "COMPLETED", "reason": None}}
        page = [{"sequence": 1, "event": event}] if after_sequence < 1 else []
        return {"events": page, "next_after_sequence": 1}


def main() -> int:
    service = lambda_entry.app.state.recon_service
    service.feed = OneEventFeed()
    print("table:", service.repo.table.name)
    print("poll (EventBridge branch):", lambda_entry.handler({"source": "aws.events"}, None))

    line = BankLine(line_id="L-SMOKE", bank_txn_id="TXN-SMOKE", value_date="2026-11-03", amount="100.00",
                    currency="EUR", counterparty_account="ACC-PAYEE-1", reference="aa4b83bf-e397-5857-96f6-6150b6914177")
    queued = lambda_entry.app.state.line_queue.submit([line])
    print("queued:", queued)

    sqs = boto3.client("sqs")
    messages = sqs.receive_message(QueueUrl=os.environ["QUEUE_URL"], MaxNumberOfMessages=10,
                                   WaitTimeSeconds=1).get("Messages", [])
    event = {"Records": [{"messageId": m["MessageId"], "eventSource": "aws:sqs", "body": m["Body"]}
                         for m in messages]}
    print("SQS batch:", lambda_entry.handler(event, None))

    stored = service.repo.get_line(service.tenant, "L-SMOKE")
    print("line:", json.dumps(stored, default=str))
    ok = stored is not None and stored["status"] == "MATCHED"
    print("SMOKE", "PASSED" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
