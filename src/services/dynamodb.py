import boto3
import os
from datetime import datetime
from botocore.exceptions import ClientError

#Initialise dynamodb resource
dynamodb = boto3.resource('dynamodb', region_name = os.getenv('AWS_DEFAULT_REGION', 'eu-north-1'))
table = dynamodb.Table('payments')

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
        return payment
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            #Payment already exists - return existing record
            return get_payment_by_id( payment['payment_id'])
        raise