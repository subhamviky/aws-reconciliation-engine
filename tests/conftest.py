import pytest
from src.setup.create_table import create_payments_table

@pytest.fixture(scope="session", autouse=True)
def setup_dynamodb_table():
    """
    Ensure the Payments table exists before any tests run.
    Runs once per test session.
    """
    create_payments_table(region="ap-south-1")
    yield
    # Optionally: teardown logic if you want to delete the table after tests
