"""reconciliation-service - FastAPI entry point (scaffolded by P0, extended by hand)."""
import logging
import os

import boto3
from e2a_adapters.workload import workload_credentials
from fastapi import FastAPI

from .routers.recon import router as recon_router, service_router
from .services.llm import build_triage_llm
from .services.queue import DirectLineQueue, SqsLineQueue
from .services.recon_service import ReconciliationService
from .services.repository import ReconRepository
from .services.ledger_client import HttpSettlementLedger
from .services.settlement_client import HttpSettlementFeed

logger = logging.getLogger("reconciliation_service")


def build_service() -> ReconciliationService:
    """Wiring from the environment the Lambda gets from infra/main.tf."""
    region = os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "eu-west-1"))
    table = boto3.resource("dynamodb", region_name=region).Table(os.getenv("TABLE_NAME", "reconciliation"))
    settlement_url = os.getenv("SETTLEMENT_API_URL", "http://localhost:8080")
    credentials = workload_credentials()      # SI-01: this service's own token to settlement-service; None unless configured
    return ReconciliationService(
        repo=ReconRepository(table),
        feed=HttpSettlementFeed(settlement_url, credentials=credentials),
        llm=build_triage_llm(),
        tenant_id=os.getenv("RECON_TENANT", "acme"),
        ledger=HttpSettlementLedger(settlement_url, credentials=credentials),
    )


def build_app(service: ReconciliationService) -> FastAPI:
    app = FastAPI(title="reconciliation-service")
    app.state.recon_service = service
    queue_url = os.getenv("QUEUE_URL")
    app.state.line_queue = (SqsLineQueue(boto3.client("sqs"), queue_url) if queue_url
                            else DirectLineQueue(service.reconcile))
    app.include_router(recon_router)
    app.include_router(service_router)

    @app.get("/health")
    def health() -> dict[str, str]:
        """Liveness probe used by the container HEALTHCHECK and the platform."""
        return {"status": "UP", "service": "reconciliation-service"}

    return app


app = build_app(build_service())
