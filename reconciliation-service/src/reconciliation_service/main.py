"""reconciliation-service - FastAPI entry point (scaffolded by P0, extended by hand)."""
import logging
import os

import boto3
from e2a_adapters.workload import workload_credentials
from fastapi import FastAPI

from .routers.gcp import router as gcp_router
from .routers.recon import router as recon_router, service_router
from .services.llm import build_triage_llm
from .services.queue import DirectLineQueue, PubSubLineQueue, SqsLineQueue
from .services.recon_service import ReconciliationService
from .services.repository import ReconRepository
from .services.ledger_client import HttpSettlementLedger
from .services.settlement_client import HttpSettlementFeed

logger = logging.getLogger("reconciliation_service")


def build_repository():
    """Where the service keeps its state: RECON_STATE_BACKEND=dynamodb (AWS, infra/) or firestore
    (Google Cloud, infra/gcp; hub design note GCP-01). Same operations, same guarantees."""
    backend = os.getenv("RECON_STATE_BACKEND", "dynamodb").lower()
    if backend == "firestore":
        from google.cloud import firestore
        from .services.repository_firestore import FirestoreReconRepository
        client = firestore.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT"),
                                  database=os.getenv("FIRESTORE_DATABASE", "(default)"))
        return FirestoreReconRepository(client, os.getenv("RECON_FIRESTORE_PREFIX", "recon"))
    if backend != "dynamodb":
        raise ValueError(f"RECON_STATE_BACKEND must be dynamodb or firestore, not {backend!r}")
    region = os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "eu-west-1"))
    return ReconRepository(boto3.resource("dynamodb", region_name=region).Table(os.getenv("TABLE_NAME", "reconciliation")))


def build_service() -> ReconciliationService:
    """Wiring from the environment: infra/main.tf (AWS Lambda) or infra/gcp (Cloud Run)."""
    settlement_url = os.getenv("SETTLEMENT_API_URL", "http://localhost:8080")
    credentials = workload_credentials()      # SI-01: this service's own token to settlement-service; None unless configured
    return ReconciliationService(
        repo=build_repository(),
        feed=HttpSettlementFeed(settlement_url, credentials=credentials),
        llm=build_triage_llm(),
        tenant_id=os.getenv("RECON_TENANT", "acme"),
        ledger=HttpSettlementLedger(settlement_url, credentials=credentials),
    )


def build_app(service: ReconciliationService) -> FastAPI:
    app = FastAPI(title="reconciliation-service")
    app.state.recon_service = service
    queue_url, topic = os.getenv("QUEUE_URL"), os.getenv("PUBSUB_LINES_TOPIC")
    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    app.state.pubsub_broker = None
    if project:                                       # Google Cloud: Pub/Sub for lines and dead letters
        from e2a_adapters.gcp import PubSubBroker
        app.state.pubsub_broker = PubSubBroker(project)
    app.state.pubsub_lines_subscription = os.getenv("PUBSUB_LINES_SUBSCRIPTION")
    if queue_url:
        app.state.line_queue = SqsLineQueue(boto3.client("sqs"), queue_url)
    elif topic and app.state.pubsub_broker is not None:
        app.state.line_queue = PubSubLineQueue(app.state.pubsub_broker, topic)
    else:
        app.state.line_queue = DirectLineQueue(service.reconcile)
    app.include_router(recon_router)
    app.include_router(service_router)
    app.include_router(gcp_router)

    @app.get("/health")
    def health() -> dict[str, str]:
        """Liveness probe used by the container HEALTHCHECK and the platform."""
        return {"status": "UP", "service": "reconciliation-service"}

    return app


app = build_app(build_service())
