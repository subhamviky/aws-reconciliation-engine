from fastapi import FastAPI
from src.api.routes import payments

app = FastAPI(
    title="Payment Reconciliation Engine",
    description="AWS-native payment reconciliation system",
    version="0.1.0"
)

app.include_router(payments.router, prefix="/payments", tags=["payments"])

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "reconciliation-engine"}