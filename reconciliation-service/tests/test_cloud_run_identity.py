"""GCP-01, E2A v1.11.0: on Cloud Run, IAM verifies the caller's Google ID token and the service
reads it from the headers. People and services alike are granted this tenant and their roles by
the deployment (E2A_IDENTITY_SUBJECT_ROLES); the token names only an email."""
import base64
import json
import sys
import types

import pytest
from fastapi.testclient import TestClient

from reconciliation_service import lambda_entry
from reconciliation_service.services.llm import build_triage_llm

ANALYST, ASSISTANT = "analyst@acme.example", "genai-app@demo.iam.gserviceaccount.com"


def b64(obj) -> str:
    return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")


def id_token(email, iss="https://accounts.google.com", tenant=None):
    token = f"{b64({'alg': 'RS256'})}.{b64({'iss': iss, 'email': email, 'sub': '7'})}.c2ln"
    return {"Authorization": f"Bearer {token}", **({"X-Tenant-Id": tenant} if tenant else {})}


@pytest.fixture
def client(service, monkeypatch):
    monkeypatch.setenv("E2A_IDENTITY_SOURCE", "gcp_cloud_run")
    monkeypatch.setenv("E2A_IDENTITY_TRUSTED_ISSUERS", '["https://accounts.google.com"]')
    monkeypatch.setenv("E2A_IDENTITY_SUBJECT_ROLES", json.dumps({
        ANALYST: ["tenant:acme"], ASSISTANT: ["tenant:acme", "reconciliation.read"]}))
    original = lambda_entry.app.state.recon_service
    lambda_entry.app.state.recon_service = service
    yield TestClient(lambda_entry.app)
    lambda_entry.app.state.recon_service = original


def test_a_granted_person_uses_the_api(client):
    assert client.get("/api/v1/exceptions", headers=id_token(ANALYST)).status_code == 200


def test_a_granted_service_uses_its_route(client):
    answer = client.get("/service/v1/exceptions", headers=id_token(ASSISTANT, tenant="acme"))
    assert answer.status_code == 200 and answer.json() == []
    # the analyst holds the tenant but not the service route's action role
    assert client.get("/service/v1/exceptions", headers=id_token(ANALYST, tenant="acme")).status_code == 403


def test_nobody_else_passes(client):
    assert client.get("/api/v1/exceptions").status_code == 401
    assert client.get("/api/v1/exceptions", headers=id_token("stranger@else.example")).status_code == 403
    assert client.get("/api/v1/exceptions", headers=id_token(ANALYST, iss="https://evil.example")).status_code == 403
    assert client.get("/service/v1/exceptions", headers=id_token(ASSISTANT, tenant="globex")).status_code == 403


def test_the_triage_model_follows_the_provider_profile(monkeypatch):
    monkeypatch.delenv("E2A_PROVIDER_PROFILE", raising=False)
    assert type(build_triage_llm()).__name__ == "SimulatedLLMService"
    fake = types.ModuleType("e2a_managed")
    fake.bindings_from_profile = lambda profile: types.SimpleNamespace(llm_service=f"model of {profile}")
    monkeypatch.setitem(sys.modules, "e2a_managed", fake)
    monkeypatch.setenv("E2A_PROVIDER_PROFILE", "gemini_api")
    assert build_triage_llm() == "model of gemini_api"
