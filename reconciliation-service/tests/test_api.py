"""HTTP surface, direct mode (no QUEUE_URL): statements are reconciled synchronously."""
from fastapi.testclient import TestClient

from conftest import line
from reconciliation_service.main import build_app


def test_statement_exception_and_accept(service, feed):
    feed.completed("S1", "250.00")
    client = TestClient(build_app(service))
    assert client.post("/api/v1/settlements/poll").json() == {"ingested": 1}
    body = client.post("/api/v1/statements", json=[line("L1", "247.50").model_dump(mode="json")]).json()
    assert body["mode"] == "direct" and body["results"][0]["status"] == "EXCEPTION"
    open_cases = client.get("/api/v1/exceptions", params={"status": "OPEN"}).json()
    assert [c["line_id"] for c in open_cases] == ["L1"]
    assert client.post("/api/v1/exceptions/L1/accept").json()["status"] == "RESOLVED"
    assert client.post("/api/v1/exceptions/L1/accept").status_code == 422     # already resolved
    assert client.get("/api/v1/lines/L1").json()["status"] == "MATCHED"
    assert client.get("/api/v1/lines/NOPE").status_code == 404
