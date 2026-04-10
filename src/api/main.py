import logging
import uuid
from fastapi import FastAPI, Request, HTTPException
from src.api.routes import payments
import logging

logging.basicConfig(
    level=logging.INFO,
    format= '%(asctime)s %(levelname)s %(name)s trace_id=%(trace_id)s %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Payment Reconciliation Engine",
    description="AWS-native payment reconciliation system",
    version="0.1.0",
    redirect_slashes=False
)

@app.middleware("http")
async def add_trace_id(request: Request, call_next):
    trace_id = str(uuid.uuid4())[:8]
    request.state.trace_id = trace_id
    import logging_context
    logging_context.trace_id = trace_id
    response = await call_next(request)
    response.headers["X-Trace=ID"] = trace_id
    return response

app.include_router(payments.router, prefix="/payments", tags=["payments"])

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "reconciliation-engine"}

from src.pipeline.rag_pipeline import run_pipeline

if __name__ == "__main__":
    run_pipeline()