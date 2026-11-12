"""reconciliation-service - FastAPI entry point (scaffolded by P0)."""
import logging

from fastapi import FastAPI

logger = logging.getLogger("reconciliation_service")

app = FastAPI(title="reconciliation-service")


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe used by the container HEALTHCHECK and the platform."""
    return {"status": "UP", "service": "reconciliation-service"}
