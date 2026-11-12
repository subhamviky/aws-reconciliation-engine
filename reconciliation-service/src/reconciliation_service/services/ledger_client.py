"""Posts accepted write-offs and refunds to the settlement ledger:
POST /api/v1/settlements/{id}/adjustments on settlement-service.

The Idempotency-Key is derived from the bank line, so a retry (or a redelivered accept)
can never post twice: settlement-service replays the first result. The outcome is typed:
  POSTED   201: the adjustment is in the ledger
  REFUSED  4xx: settlement-service's own rules said no (for example its write-off limit)
  PENDING  no definitive answer (5xx, timeout, connection): retried later with the same key
"""
from decimal import Decimal
from typing import Dict, Protocol

import httpx
from e2a_base import CircuitBreaker, RetryBudget

from ..generated.nfr import call_with_resilience


def ledger_key(tenant_id: str, line_id: str) -> str:
    return f"recon-{tenant_id}-{line_id}"


class SettlementLedger(Protocol):
    def post_adjustment(self, tenant_id: str, request: Dict) -> Dict: ...


class HttpSettlementLedger:
    def __init__(self, base_url: str, timeout: float = 5.0, transport=None) -> None:
        self._http = httpx.Client(base_url=base_url, timeout=timeout, transport=transport)
        self._breaker = CircuitBreaker(failure_threshold=5, reset_seconds=30.0)
        self._budget = RetryBudget()

    def post_adjustment(self, tenant_id: str, request: Dict) -> Dict:
        body = {k: request[k] for k in ("type", "amount", "reason", "reference")}

        def call() -> httpx.Response:
            r = self._http.post(f"/api/v1/settlements/{request['settlement_id']}/adjustments", json=body,
                                headers={"X-Tenant-Id": tenant_id, "Idempotency-Key": request["key"]})
            if r.status_code >= 500 or (r.status_code == 409 and "in progress" in r.text):
                raise RuntimeError(f"settlement-service answered {r.status_code}")   # not definitive
            return r
        try:
            response = call_with_resilience(call, self._breaker, self._budget, retries=2)
        except Exception as error:                                   # transport failure or 5xx after retries
            return {"outcome": "PENDING", "detail": str(error)}
        data = response.json() if response.content else {}
        if response.status_code == 201:
            return {"outcome": "POSTED", "adjustment_id": data.get("adjustmentId"),
                    "detail": f"{data.get('type')} {data.get('amount')}: {data.get('debitAccount')} -> "
                              f"{data.get('creditAccount')}"}
        return {"outcome": "REFUSED", "detail": f"HTTP {response.status_code}: {data.get('error') or data}"}


def adjustment_request(tenant_id: str, line_id: str, kind: str, settlement_id: str, amount: Decimal,
                       reason: str) -> Dict:
    return {"key": ledger_key(tenant_id, line_id), "settlement_id": settlement_id, "type": kind,
            "amount": str(amount.quantize(Decimal("0.01"))), "reason": reason, "reference": line_id}
