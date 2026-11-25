"""Google Cloud entry points (hub design note GCP-01); the AWS Lambda handler's two other roles.

  POST /pubsub/bank-lines   a Pub/Sub push of one bank line: E2A's IdempotentConsumer settles it
                            (PubSubPushDelivery). 204: done, a duplicate, or dead-lettered with its
                            reason to <subscription>-dlq. 500: Pub/Sub delivers it again.
  POST /jobs/scheduled      Cloud Scheduler: poll the settlement feed, retry pending ledger postings,
                            and reconcile the dead letters (each confirmed against the repository and
                            replayed only if it never took effect) under the service's lease.

Both are reached only by their callers' identities: Cloud Run IAM admits the push subscription's
and the scheduler's service accounts (infra/gcp), and nothing else.
"""
import logging

from fastapi import APIRouter, HTTPException, Request, Response

from ..services.line_consumer import BankLineConsumer
from ..services.recon_service import CONSUMER_CONFIG

logger = logging.getLogger("reconciliation_service")
router = APIRouter()


def _broker(request: Request):
    broker = getattr(request.app.state, "pubsub_broker", None)
    if broker is None:
        raise HTTPException(503, "Pub/Sub is not configured (GOOGLE_CLOUD_PROJECT)")
    return broker


@router.post("/pubsub/bank-lines")
async def pubsub_bank_line(request: Request) -> Response:
    from e2a_adapters.gcp import PubSubPushDelivery
    try:
        delivery = PubSubPushDelivery(await request.json(), _broker(request))
    except ValueError as error:                      # not a push envelope: Pub/Sub never sends one
        raise HTTPException(400, str(error))
    report = BankLineConsumer(request.app.state.recon_service, delivery).consume(delivery.source, CONSUMER_CONFIG)
    for settled in report["messages"]:
        if settled["decision"] in ("retried", "dead_lettered"):
            logger.warning("bank line %s %s: %s", settled["idempotency_key"] or settled["message_id"],
                           settled["decision"], settled["reason"])
    return Response(status_code=delivery.response_status())


@router.post("/jobs/scheduled")
def scheduled(request: Request) -> dict:
    service = request.app.state.recon_service
    result = {"ingested": service.poll_settlements(), "ledger_posted": service.retry_ledger_postings()}
    subscription = getattr(request.app.state, "pubsub_lines_subscription", None)
    if subscription:
        reconciled = BankLineConsumer(service, _broker(request), subscription, lock=service.lease) \
            .reconcile(CONSUMER_CONFIG, dlq_source=subscription)
        result["dead_letters"] = {k: reconciled.get(k) for k in ("status", "replayed", "unresolved")}
    return result
