from src.clients.dynamodb_client import put_payment_item, update_payment_status
from src.clients.bedrock_client import get_bedrock_embeddings

def run_pipeline():
    # Insert item
    put_payment_item("TEST-001", "PENDING")
    print("Item inserted successfully")

    # Update item
    update_payment_status("TEST-001", "COMPLETED")
    print("Item updated successfully")

    # Generate embedding
    embeddings = get_bedrock_embeddings()
    vector = embeddings.embed_query("Hello world")
    print("Embedding vector length:", len(vector))
