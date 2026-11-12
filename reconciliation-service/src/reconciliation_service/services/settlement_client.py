"""Reads the settlement-service event feed (contracts/vendor/settlement-event.v1.schema.json).
Every call goes through the A2C-generated resilience wrapper (breaker + bounded retry)."""
from typing import Any, Dict, List, Protocol

import httpx
from e2a_base import CircuitBreaker, RetryBudget

from ..generated.nfr import call_with_resilience


class SettlementFeed(Protocol):
    def events_after(self, tenant_id: str, after_sequence: int) -> Dict[str, Any]: ...


class HttpSettlementFeed:
    def __init__(self, base_url: str, timeout: float = 5.0) -> None:
        self._http = httpx.Client(base_url=base_url, timeout=timeout)
        self._breaker = CircuitBreaker(failure_threshold=5, reset_seconds=30.0)
        self._budget = RetryBudget()

    def events_after(self, tenant_id: str, after_sequence: int) -> Dict[str, Any]:
        def call() -> Dict[str, Any]:
            r = self._http.get("/api/v1/events", params={"afterSequence": after_sequence, "limit": 100},
                               headers={"X-Tenant-Id": tenant_id})
            r.raise_for_status()
            return r.json()
        return call_with_resilience(call, self._breaker, self._budget)


def events_from(feed: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [item["event"] for item in feed.get("events", [])]
