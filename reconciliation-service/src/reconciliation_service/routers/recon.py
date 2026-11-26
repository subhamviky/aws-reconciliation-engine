"""HTTP surface of the reconciliation engine (API Gateway -> Lambda via Mangum). Every route
requires the identity API Gateway verified when identity at ingress is on (routers/identity.py)."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..models.records import BankLine, ExceptionCase
from ..services.recon_service import ConcurrentChange, LedgerUnavailable, ProposalRejected

from .identity import require_identity, service_identity

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_identity)])


@router.post("/statements", status_code=202)
def submit_statement(lines: List[BankLine], request: Request) -> dict:
    queue = request.app.state.line_queue
    return {"mode": queue.mode, "results": queue.submit(lines)}


@router.post("/settlements/poll")
def poll_settlements(request: Request) -> dict:
    return {"ingested": request.app.state.recon_service.poll_settlements()}


@router.post("/ledger/retry")
def retry_ledger(request: Request) -> dict:
    """Re-send pending write-off and refund postings now (the schedule does it every 5 minutes)."""
    return {"posted": request.app.state.recon_service.retry_ledger_postings()}


@router.get("/lines/{line_id}")
def get_line(line_id: str, request: Request) -> dict:
    service = request.app.state.recon_service
    line = service.repo.get_line(service.tenant, line_id)
    if line is None:
        raise HTTPException(status_code=404, detail="unknown line")
    return line


@router.get("/exceptions", response_model=List[ExceptionCase])
def list_exceptions(request: Request, status: Optional[str] = None) -> List[ExceptionCase]:
    return request.app.state.recon_service.exceptions(status)


@router.post("/exceptions/{line_id}/accept")
def accept_proposal(line_id: str, request: Request) -> dict:
    try:
        return request.app.state.recon_service.accept(line_id)
    except ProposalRejected as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ConcurrentChange as e:
        raise HTTPException(status_code=409, detail=str(e))


# Service callers (hub design note SI-01): o2c-agent-service reads open exceptions here, with an
# Entra token API Gateway verified (a separate authorizer from the users' one).
service_router = APIRouter(prefix="/service/v1")


@service_router.get("/exceptions", response_model=List[ExceptionCase],
                    dependencies=[Depends(service_identity("reconciliation.read"))])
def list_exceptions_for_services(request: Request, status: Optional[str] = None) -> List[ExceptionCase]:
    return request.app.state.recon_service.exceptions(status)


class ResolveBody(BaseModel):
    settlement_id: str
    adjustment_id: str


@service_router.post("/exceptions/{line_id}/resolve", dependencies=[Depends(service_identity("reconciliation.resolve"))])
def resolve_for_services(line_id: str, body: ResolveBody, request: Request) -> dict:
    """Close an exception whose adjustment another system posted after an approval (hub design note GCP-02, A.1): the
    ledger is read and the exception closes only if it shows that adjustment for this bank line."""
    try:
        return request.app.state.recon_service.resolve_with_adjustment(line_id, body.settlement_id, body.adjustment_id)
    except ProposalRejected as e:
        raise HTTPException(status_code=422, detail=str(e))
    except LedgerUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))


@service_router.get("/lines/{line_id}", dependencies=[Depends(service_identity("reconciliation.read"))])
def get_line_for_services(line_id: str, request: Request) -> dict:
    """One bank line (its amount, counterparty and status), for the services that explain an exception:
    the exception names the line, the line says what was paid (hub design note GCP-01)."""
    service = request.app.state.recon_service
    line = service.repo.get_line(service.tenant, line_id)
    if line is None:
        raise HTTPException(status_code=404, detail="unknown line")
    return line
