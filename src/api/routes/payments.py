from src.utils.logger import get_logger, log_event, generate_trace_id
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime
import uuid
import boto3
import json
from src.services.dynamodb import(
    save_payment,
    get_payment_by_id,
    get_payment_by_reference
)

logger = get_logger(__name__)

router = APIRouter()
SQS_QUEUE_URL = "https://sqs.ap-south-1.amazonaws.com/494899930475/payments-queue"

class PaymentRequest(BaseModel):
    vendor_id:str
    amount:float
    currency:str = 'USD'
    reference_id: str

class PaymentResponse(BaseModel):
    payment_id: str
    vendor_id: str
    amount: float
    currency: str
    reference_id: str
    status:str
    created_at:str

@router.post("/", response_model = PaymentResponse)
def create_payment(payment: PaymentRequest):
    trace_id = generate_trace_id()

    log_event(logger, "payment received", trace_id,
                vendor_id=payment.vendor_id,
                reference_id=payment.reference_id,
                amount = str(payment.amount))

    "Submit payment for reconciliation"
    existing = get_payment_by_reference(payment.reference_id)
    if existing:
        log_event(logger, "duplicate_payment_blocked", trace_id,
                    reference_id = payment.reference_id)
        return PaymentResponse(**existing)
    new_payment = {
        'payment_id' : str(uuid.uuid4()),
        'vendor_id' : payment.vendor_id,
        'amount' : str(payment.amount),
        'currency' : payment.currency,
        'reference_id' : payment.reference_id,
        'status' : 'PENDING',
        'created_at' : datetime.utcnow().isoformat()
    }
    saved = save_payment(new_payment)
    # Drop message onto SQS for async processing
    sqs = boto3.client('sqs', region_name='ap-south-1')
    sqs.send_message(
        QueueUrl=SQS_QUEUE_URL,
        MessageBody=json.dumps(new_payment)
    )

    log_event(logger, "payment_queued", trace_id,
                payment_id=new_payment["payment_id"],
                status = "PENDING")
    return PaymentResponse(**saved)

@router.get("/{payment_id}", response_model = PaymentResponse)
async def get_payment(payment_id:str):
    "Retrieve payment by id"
    payment = get_payment_by_id(payment_id)
    if not payment:
        raise HTTPException(status_code = 404, detail = 'Payment not found')
    return PaymentResponse(**payment)

@router.post("/reconcile/{payment_id}")
def reconcile(payment_id:str):
    payment = get_payment_by_id(payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table("payments")

    table.update_item(
        Key={"payment_id": payment_id},
        UpdateExpression="SET #s = :new_status",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":new_status": "RECONCILED"}
    )

    return{"payment_id" : payment_id, "status" : "RECONCILED" }

from src.agents.payment_agent import app as payment_agent_app

class QueryRequest(BaseModel):
    question:str

@router.post("/query")
def query_payments(request: QueryRequest):
    "Natural Language"
    trace_id = generate_trace_id()
    log_event(logger, "agent_query_received", trace_id,
                question=request.question)
    result = payment_agent_app.invoke({
        "query": request.question,
        "intent": "",
        "rag_context": "",
        "tool_result": "",
        "final_response": "",
        "trace_id": trace_id
    })
    log_event(logger, "agent_query_complete", trace_id,
                intent = result.get("intent") )
    return {"answer" : result["final_response"], "trace_id": trace_id}
