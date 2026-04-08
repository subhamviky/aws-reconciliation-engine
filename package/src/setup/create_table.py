from src.clients.dynamodb_client import get_dynamodb_client

def create_payments_table(region="ap-south-1"):
    dynamodb = get_dynamodb_client(region)

    try:
        response = dynamodb.create_table(
            TableName="Payments",
            AttributeDefinitions=[
                {"AttributeName": "payment_id", "AttributeType": "S"}
            ],
            KeySchema=[
                {"AttributeName": "payment_id", "KeyType": "HASH"}
            ],
            ProvisionedThroughput={
                "ReadCapacityUnits": 5,
                "WriteCapacityUnits": 5
            }
        )
        print("Creating table…")
        dynamodb.get_waiter("table_exists").wait(TableName="Payments")
        print("Table created successfully:", response["TableDescription"]["TableName"])
    except dynamodb.exceptions.ResourceInUseException:
        print("Table 'Payments' already exists in region", region)

if __name__ == "__main__":
    create_payments_table()
