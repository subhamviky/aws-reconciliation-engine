"""Bank lines under E2A's IdempotentConsumer (E2A v1.7.2, hub design note MP-05).

Every bank line, whatever path it comes by, is settled by one consumer under one E2A claim on
its line_id (DynamoDB, e2a-adapters):

    SQS  -> Lambda batch          SQSLambdaBatch: failed records go back in batchItemFailures,
                                  poison ones to the dead-letter queue with the reason
    HTTP / local                  ReconciliationService.reconcile(line): the same consumer
                                  settles the one line it publishes on an in-process broker
    EventBridge schedule          reconcile(): each dead letter is confirmed against the
                                  repository first, and replayed only if it never took effect

The handler is resumable (process_line() checks what an earlier delivery already stored), so a
redelivery may take over a claim whose Lambda stopped (consumer_resume_expired).
"""
from typing import Any, Dict

from e2a import IdempotentConsumer, PhysicalOutcome

from ..models.records import BankLine


class BankLineConsumer(IdempotentConsumer):
    def __init__(self, service, broker, source: str = None, lock=None) -> None:
        super().__init__(broker, service.claims, source, lock)
        self.service = service

    def _tenant_of(self, message):
        return self.service.tenant                  # one tenant per deployment (RECON_TENANT)

    def _idempotency_key(self, message):
        if message.attributes.get("e2a_body_error"):
            return None                             # not JSON: dead-lettered with the reason
        return message.body.get("line_id")

    def _handle(self, message, config, tenant_id, idempotency_key) -> Dict[str, Any]:
        line = BankLine.model_validate(message.body)   # a ValidationError is a ValueError: dead-lettered
        return {**self.service.process_line(line), "physical_success": True}

    def _confirm(self, message, config) -> PhysicalOutcome:
        """A dead letter's line took effect if the repository holds its outcome."""
        line_id = message.body.get("line_id")
        if line_id and self.service.outcome_of(line_id) is not None:
            return PhysicalOutcome.COMMITTED
        return PhysicalOutcome.NOT_COMMITTED
