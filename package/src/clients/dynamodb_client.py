import boto3

def get_dynamodb_client(region="ap-south-1"):
    return boto3.client("dynamodb", region_name=region)

def put_payment_item(payment_id, status, region="ap-south-1"):
    dynamodb = get_dynamodb_client(region)
    dynamodb.put_item(
        TableName="Payments",
        Item={
            "payment_id": {"S": payment_id},
            "status": {"S": status}
        }
    )

def update_payment_status(payment_id, new_status, region="ap-south-1"):
    dynamodb = get_dynamodb_client(region)
    dynamodb.update_item(
        TableName="Payments",
        Key={"payment_id": {"S": payment_id}},
        UpdateExpression="SET #s = :new_status",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":new_status": {"S": new_status}}
    )