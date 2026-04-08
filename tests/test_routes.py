import pytest
from src.setup.create_table import create_payments_table
from src.clients.dynamodb_client import get_dynamodb_client
from src.pipeline.rag_pipeline import run_pipeline

@pytest.fixture(scope="session", autouse=True)
def setup_dynamodb_table():
    """
    Ensure the Payments table exists in ap-south-1 before any tests run.
    """
    create_payments_table(region="ap-south-1")
    yield

def test_payment_lifecycle():
    """
    Test the full lifecycle: insert item, update item, generate embedding.
    """
    run_pipeline()
    client = get_dynamodb_client(region="ap-south-1")
    resp = client.get_item(TableName="Payments", Key={"payment_id": {"S": "TEST-001"}})
    assert resp["Item"]["status"]["S"] == "COMPLETED"

def test_multiple_updates():
    """
    Test that multiple updates on the same item work correctly.
    """
    client = get_dynamodb_client(region="ap-south-1")

    client.update_item(
        TableName="Payments",
        Key={"payment_id": {"S": "TEST-001"}},
        UpdateExpression="SET #s = :new_status",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":new_status": {"S": "FAILED"}}
    )
    resp1 = client.get_item(TableName="Payments", Key={"payment_id": {"S": "TEST-001"}})
    assert resp1["Item"]["status"]["S"] == "FAILED"

    client.update_item(
        TableName="Payments",
        Key={"payment_id": {"S": "TEST-001"}},
        UpdateExpression="SET #s = :new_status",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":new_status": {"S": "RETRY"}}
    )
    resp2 = client.get_item(TableName="Payments", Key={"payment_id": {"S": "TEST-001"}})
    assert resp2["Item"]["status"]["S"] == "RETRY"

def test_reconcile_payment():
    """
    Test reconciliation: mark a payment as SETTLED.
    """
    client = get_dynamodb_client(region="ap-south-1")
    client.update_item(
        TableName="Payments",
        Key={"payment_id": {"S": "TEST-001"}},
        UpdateExpression="SET #s = :new_status",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":new_status": {"S": "SETTLED"}}
    )
    resp = client.get_item(TableName="Payments", Key={"payment_id": {"S": "TEST-001"}})
    assert resp["Item"]["status"]["S"] == "SETTLED"

def test_get_payments():
    """
    Test retrieval: scan all payments and verify at least one exists.
    """
    client = get_dynamodb_client(region="ap-south-1")
    resp = client.scan(TableName="Payments")
    items = resp.get("Items", [])
    assert len(items) > 0
    # Optional: check that TEST-001 is among them
    ids = [item["payment_id"]["S"] for item in items]
    assert "TEST-001" in ids