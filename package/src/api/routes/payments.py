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
    "Submit payment for reconciliation"
    existing = get_payment_by_reference(payment.reference_id)
    if existing:
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
    return PaymentResponse(**saved)

@router.get("/{payment_id}", response_model = PaymentResponse)
def get_payment(payment_id:str):
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
