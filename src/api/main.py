from fastapi import FastAPI
from src.api.routes import payments

app = FastAPI(
    title="Payment Reconciliation Engine",
    description="AWS-native payment reconciliation system",
    version="0.1.0",
    redirect_slashes=False
)

app.include_router(payments.router, prefix="/payments", tags=["payments"])

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "reconciliation-engine"}

from src.pipeline.rag_pipeline import run_pipeline

if __name__ == "__main__":
    run_pipeline()