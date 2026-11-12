"""HTTP surface of the reconciliation engine (API Gateway -> Lambda via Mangum)."""
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request

from ..models.records import BankLine, ExceptionCase
from ..services.recon_service import ConcurrentChange, ProposalRejected

router = APIRouter(prefix="/api/v1")


@router.post("/statements", status_code=202)
def submit_statement(lines: List[BankLine], request: Request) -> dict:
    queue = request.app.state.line_queue
    return {"mode": queue.mode, "results": queue.submit(lines)}


@router.post("/settlements/poll")
def poll_settlements(request: Request) -> dict:
    return {"ingested": request.app.state.recon_service.poll_settlements()}


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
