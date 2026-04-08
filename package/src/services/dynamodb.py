from src.utils.logger import get_logger, log_event
import boto3
import os
from datetime import datetime
from botocore.exceptions import ClientError

logger = get_logger(__name__)

#Initialise dynamodb resource
dynamodb = boto3.resource('dynamodb', region_name='ap-south-1')
table = dynamodb.Table(os.getenv('DYNAMODB_TABLE_NAME', 'payments'))    

def get_payment_by_id(payment_id: str):
    "Fetch payment by primary key"
    try:
        response = table.get_item(Key = { 'payment_id' : payment_id} )
        return response.get('Item')
    except ClientError as e:
        print(f"Error fetching payment: {e}" )
        raise

def get_payment_by_reference(reference_id: str):
    "Fetch payment by reference already exists"
    try:
        from boto3.dynamodb.conditions import Key
        response = table.query(
                    IndexName = 'reference_id-index',
                    KeyConditionExpression = Key('reference_id').eq(reference_id)
        )
        items = response.get('Items', [])
        return items[0] if items else None
    except ClientError as e:
        print(f"Error querying by reference: {e}")
        raise

def save_payment(payment: dict):
    "Save payments to dynamoDB"
    try:
        table.put_item(
            Item = payment,
            ConditionExpression = 'attribute_not_exists(payment_id)'
        )
        log_event(logger, "payment saved", payment.get("payment_id", "unknown"),
                payment_id = payment.get("payment_id"))
        return payment
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            log_event(logger, "idempotency_check_passed", "system",
                    payment_id = payment.get("payment_id"))
            #Payment already exists - return existing record
            return get_payment_by_id( payment['payment_id'])
        raise