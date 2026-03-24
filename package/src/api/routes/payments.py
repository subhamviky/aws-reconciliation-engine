from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime
import uuid
from src.services.dynamodb import(
    save_payment,
    get_payment_by_id,
    get_payment_by_reference
)

router = APIRouter()

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
    return PaymentResponse(**saved)

@router.get("/{payment_id}", response_model = PaymentResponse)
def get_payment(payment_id:str):
    "Retrieve payment by id"
    payment = get_payment_by_id(payment_id)
    if not payment:
        raise HTTPException(status_code = 404, detail = 'Payment not found')
    return PaymentResponse(**payment)