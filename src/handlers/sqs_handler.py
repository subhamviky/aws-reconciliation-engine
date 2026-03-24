import os
import json
import boto3

dynamodb = boto3.resource("dynamodb", region_name=os.getenv("AWS_REGION", "ap-south-1"))
table = dynamodb.Table(os.getenv("DYNAMODB_TABLE_NAME", "payments"))

def process_payment_record(record):
    body = json.loads(record["body"])
    payment_id = body.get("payment_id")

    table.update_item(
        Key={"payment_id": payment_id},
        UpdateExpression="SET #status = :val",
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={":val": "RECONCILED"}
    )

def handler(event, context):
    for record in event["Records"]:
        try:
            process_payment_record(record)
            print(f"Processed record: {record['messageId']}")
        except Exception as e:
            print(f"Error processing record: {e}")
            raise e

    return {
        "statusCode": 200,
        "body": "Processed SQS messages successfully"
    }
