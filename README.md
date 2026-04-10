# Cloud-Native Payment Reconciliation Engine

Live on AWS — ap-south-1

## What This Is
A production-grade payment reconciliation engine built on AWS, directly mirroring 
$350M SAP TM financial settlement architecture on cloud-native infrastructure.

## Architecture
POST /payments → API Gateway → Lambda (FastAPI) → DynamoDB + SQS
SQS → Lambda Consumer → status update → RECONCILED
Natural language query → LangGraph Agent → RAG (Bedrock Titan) → grounded answer

## AWS Services
- Lambda + Mangum — serverless FastAPI deployment
- API Gateway — HTTP API with rate limiting
- DynamoDB — payments table, PAY_PER_REQUEST, GSI for idempotency
- SQS + DLQ — async payment processing with failure escalation  
- CloudWatch — structured logging with correlation ID threading
- Amazon Bedrock — Titan embeddings for RAG pipeline

## Key Engineering Decisions
- Two-layer idempotency: application-level GSI query + DB-level condition expression
- Async pattern: POST returns PENDING immediately, SQS consumer processes async
- LangGraph agent routes queries: REF-xxx → DynamoDB tool call, open questions → RAG

## Run Locally
```bash
source venv/bin/activate
uvicorn src.api.main:app --reload
# Swagger UI: http://localhost:8000/docs
```

## Deploy to AWS
```bash
./deploy.sh
```

## AWS → GCP Mapping
| AWS | GCP |
|-----|-----|
| Lambda | Cloud Run |
| Bedrock | Vertex AI |
| SQS | Pub/Sub |
| DynamoDB | Firestore |
| CloudWatch | Cloud Monitoring |
