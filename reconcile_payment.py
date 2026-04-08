import boto3

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table("payments")

table.update_item(
    Key={"payment_id": "6aeea6b4-b311-4e1e-a8d5-d86f9f3e2c5f"},
    UpdateExpression="SET #s = :new_status",
    ExpressionAttributeNames={"#s": "status"},
    ExpressionAttributeValues={":new_status": "RECONCILED"}
)