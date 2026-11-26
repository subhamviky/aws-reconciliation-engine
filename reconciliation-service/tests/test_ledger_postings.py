"""Accepted write-offs and refunds reach the settlement ledger exactly once, with retries."""
from decimal import Decimal

import httpx
import pytest

from conftest import ACCOUNT, TENANT, line, sid
from reconciliation_service.services.ledger_client import HttpSettlementLedger


class FakeLedger:
    """Answers like settlement-service; replays a key it has seen (its idempotency)."""

    def __init__(self) -> None:
        self.mode, self.calls, self.posted = "ok", [], {}

    def post_adjustment(self, tenant_id, request):
        self.calls.append(dict(request))
        if self.mode == "down":
            return {"outcome": "PENDING", "detail": "connection refused"}
        if self.mode == "refuse":
            return {"outcome": "REFUSED", "detail": "HTTP 422: exceeds the write-off limit"}
        self.posted.setdefault(request["key"], f"adj-{len(self.posted) + 1}")
        return {"outcome": "POSTED", "adjustment_id": self.posted[request["key"]], "detail": "ok"}


@pytest.fixture
def ledger(service):
    service.ledger = FakeLedger()
    return service.ledger


def test_an_accepted_write_off_is_posted_to_the_ledger(service, feed, ledger):
    feed.completed("S1", "250.00")
    service.poll_settlements()
    service.reconcile(line("L1", "247.50"))
    result = service.accept("L1")
    assert result["ledger_status"] == "POSTED"
    [call] = ledger.calls
    assert (call["type"], call["settlement_id"], call["amount"], call["reference"]) == \
        ("WRITE_OFF", sid("S1"), "2.50", "L1")
    assert call["key"] == f"recon-{TENANT}-L1"
    assert service.repo.get_exception(TENANT, "L1").ledger_adjustment_id == "adj-1"


def test_an_exact_match_posts_nothing(service, feed, ledger):
    feed.completed("S1", "100.00")
    service.poll_settlements()
    service.reconcile(line("L1", "100.00"))
    assert ledger.calls == []


def test_an_accepted_refund_is_posted_against_the_original_settlement(service, feed, ledger):
    feed.completed("S1", "100.00")
    service.poll_settlements()
    service.reconcile(line("L1", "100.00", txn="T-1"))
    service.reconcile(line("L2", "100.00", txn="T-1", day=4))
    assert service.accept("L2")["ledger_status"] == "POSTED"
    [call] = ledger.calls
    assert (call["type"], call["settlement_id"], call["amount"]) == ("REFUND", sid("S1"), "100.00")


def test_a_refund_waits_until_the_original_payment_is_matched(service, feed, ledger):
    service.reconcile(line("L1", "70.00", txn="T-9"))           # no open item: the original is an exception
    result = service.reconcile(line("L2", "70.00", txn="T-9", day=4))
    case = service.repo.get_exception(TENANT, "L2")
    assert result["kind"] == "DUPLICATE" and result["agent_proposal_valid"] is False
    assert "original payment is matched" in case.validation_reason
    assert case.proposal.action == "REQUEST_REMITTANCE" and ledger.calls == []


def test_a_ledger_outage_is_pending_and_retried_with_the_same_key(service, feed, ledger):
    feed.completed("S1", "250.00")
    service.poll_settlements()
    service.reconcile(line("L1", "247.50"))
    ledger.mode = "down"
    accepted = service.accept("L1")
    assert accepted["status"] == "RESOLVED" and accepted["ledger_status"] == "PENDING"
    assert service.retry_ledger_postings() == 0                   # still down
    ledger.mode = "ok"
    assert service.retry_ledger_postings() == 1
    assert service.retry_ledger_postings() == 0                   # nothing pending any more
    assert len({c["key"] for c in ledger.calls}) == 1 and len(ledger.posted) == 1
    assert service.repo.get_exception(TENANT, "L1").ledger_status == "POSTED"


def test_a_refusal_by_the_ledger_is_recorded_and_not_retried(service, feed, ledger):
    feed.completed("S1", "250.00")
    service.poll_settlements()
    service.reconcile(line("L1", "247.50"))
    ledger.mode = "refuse"
    assert service.accept("L1")["ledger_status"] == "REFUSED"
    assert service.retry_ledger_postings() == 0 and len(ledger.calls) == 1
    assert "write-off limit" in service.repo.get_exception(TENANT, "L1").ledger_detail


@pytest.mark.parametrize("status, body, outcome", [
    (201, {"adjustmentId": "a-1", "type": "WRITE_OFF", "amount": 2.5, "debitAccount": ACCOUNT,
           "creditAccount": "ACC-WRITEOFF"}, "POSTED"),
    (422, {"error": "exceeds the write-off limit"}, "REFUSED"),
    (503, {"error": "unavailable"}, "PENDING"),
])
def test_the_http_client_maps_settlement_answers_to_outcomes(status, body, outcome):
    seen = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json=body)

    client = HttpSettlementLedger("http://settlement.test", transport=httpx.MockTransport(handle))
    result = client.post_adjustment(TENANT, {"key": "recon-acme-L1", "settlement_id": sid("S1"), "type": "WRITE_OFF",
                                             "amount": "2.50", "reason": "short", "reference": "L1"})
    assert result["outcome"] == outcome
    assert seen[0].url.path == f"/api/v1/settlements/{sid('S1')}/adjustments"
    assert seen[0].headers["Idempotency-Key"] == "recon-acme-L1" and seen[0].headers["X-Tenant-Id"] == TENANT


# ---------------------------------------------------- an adjustment posted by another system closes the exception
class LedgerWithRows(FakeLedger):
    """A ledger that also lists what is in it, as settlement-service does."""

    def __init__(self, rows=None, readable=True):
        super().__init__()
        self.rows, self.readable = rows or [], readable

    def adjustments(self, tenant_id, settlement_id):
        return list(self.rows) if self.readable else None


def _open_short_line(service, feed):
    feed.completed("S1", "250.00")
    service.poll_settlements()
    service.reconcile(line("L1", "247.50"))                       # an exception, not accepted here


def _row(adjustment_id="adj-9", reference="genai:L1:abc", kind="WRITE_OFF", amount="2.50"):
    return {"adjustmentId": adjustment_id, "type": kind, "amount": amount, "reference": reference}


def test_the_exception_closes_when_the_ledger_shows_the_adjustment_for_this_line(service, feed):
    service.ledger = LedgerWithRows([_row()])
    _open_short_line(service, feed)
    result = service.resolve_with_adjustment("L1", sid("S1"), "adj-9")
    case = service.repo.get_exception(TENANT, "L1")
    assert result["status"] == "RESOLVED" and result["replayed"] is False and result["adjustment_id"] == "adj-9"
    assert case.status == "RESOLVED" and case.ledger_adjustment_id == "adj-9" and "adj-9" in case.resolution
    assert service.repo.get_line(TENANT, "L1")["status"] == "ADJUSTED"
    assert service.ledger.calls == []                              # reconciliation posted nothing itself


def test_closing_it_again_with_the_same_adjustment_is_a_replay_and_another_adjustment_is_refused(service, feed):
    from reconciliation_service.services.recon_service import ProposalRejected
    service.ledger = LedgerWithRows([_row(), _row("adj-10")])
    _open_short_line(service, feed)
    service.resolve_with_adjustment("L1", sid("S1"), "adj-9")
    assert service.resolve_with_adjustment("L1", sid("S1"), "adj-9")["replayed"] is True
    with pytest.raises(ProposalRejected, match="another adjustment"):
        service.resolve_with_adjustment("L1", sid("S1"), "adj-10")


def test_the_caller_is_not_believed_without_the_ledger(service, feed):
    from reconciliation_service.services.recon_service import LedgerUnavailable, ProposalRejected
    _open_short_line(service, feed)
    service.ledger = LedgerWithRows([_row(reference="genai:L2:abc")])        # an adjustment, but for another line
    with pytest.raises(ProposalRejected, match="no such adjustment"):
        service.resolve_with_adjustment("L1", sid("S1"), "adj-9")
    service.ledger = LedgerWithRows([])                                        # none at all
    with pytest.raises(ProposalRejected):
        service.resolve_with_adjustment("L1", sid("S1"), "adj-9")
    service.ledger = LedgerWithRows([_row()], readable=False)                  # cannot be read: not "none"
    with pytest.raises(LedgerUnavailable):
        service.resolve_with_adjustment("L1", sid("S1"), "adj-9")
    assert service.repo.get_exception(TENANT, "L1").status == "OPEN"          # nothing changed


def test_an_unknown_line_has_nothing_to_resolve(service, feed):
    from reconciliation_service.services.recon_service import ProposalRejected
    service.ledger = LedgerWithRows([_row()])
    with pytest.raises(ProposalRejected, match="no exception"):
        service.resolve_with_adjustment("L-NOPE", sid("S1"), "adj-9")
