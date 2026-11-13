"""E2A claims and leases on DynamoDB (e2a-adapters, design note D-02).

Before this change, an invocation that stopped after storing the bank line and before deciding
it left the line RECEIVED forever: every redelivery answered ALREADY_RECEIVED. Now the line is
processed under an E2A claim whose lease expires before SQS redelivers, so the next delivery
takes it over and finishes it."""
import pytest

from conftest import ACCOUNT, TENANT, line, sid
from e2a import ClaimStatus
from e2a.port_contract import FakeClock
from e2a_adapters.aws import DynamoDBIdempotencyStore, DynamoDBLease
from reconciliation_service.services import recon_service as rs
from reconciliation_service.services.llm import build_triage_llm
from reconciliation_service.services.queue import DirectLineQueue
from reconciliation_service.services.recon_service import LineConflict, LineInProgress, ReconciliationService
from reconciliation_service.services.repository import ReconRepository


class LambdaKilled(BaseException):
    """The invocation stops (timeout, out of memory): nothing after it runs, not even except Exception."""


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def service(table, feed, clock):
    return ReconciliationService(ReconRepository(table), feed, build_triage_llm(), TENANT,
                                 claims=DynamoDBIdempotencyStore(table, clock=clock),
                                 lease=DynamoDBLease(table, clock=clock))


def stop_once(monkeypatch, obj, name):
    real = getattr(obj, name)
    calls = {"n": 0}

    def stopping(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise LambdaKilled()
        return real(*args, **kwargs)
    monkeypatch.setattr(obj, name, stopping)


def test_a_line_whose_invocation_stopped_after_storing_it_is_finished_by_the_next_delivery(
        service, feed, clock, monkeypatch):
    feed.completed("S1", "100.00")
    service.poll_settlements()
    stop_once(monkeypatch, service.matcher, "decide")              # stops after add_line, before the match
    with pytest.raises(LambdaKilled):
        service.reconcile(line("L1", "100.00", reference=sid("S1")))
    assert service.repo.get_line(TENANT, "L1")["status"] == "RECEIVED"

    with pytest.raises(LineInProgress):                            # an immediate redelivery waits
        service.reconcile(line("L1", "100.00", reference=sid("S1")))
    clock.advance(rs.LINE_CLAIM_LEASE_SECONDS + 1)                 # SQS redelivers after its visibility timeout
    result = service.reconcile(line("L1", "100.00", reference=sid("S1")))
    assert result["status"] == "MATCHED" and result["settlement_ids"] == [sid("S1")]
    assert service.repo.get_line(TENANT, "L1")["status"] == "MATCHED"
    assert service.repo.get_open_item(TENANT, ACCOUNT, sid("S1")).status == "MATCHED"
    assert service.reconcile(line("L1", "100.00", reference=sid("S1")))["outcome"]["status"] == "MATCHED"


def test_a_line_matched_just_before_the_invocation_stopped_is_not_matched_twice(service, feed, clock, monkeypatch):
    feed.completed("S1", "100.00")
    service.poll_settlements()
    stop_once(monkeypatch, service.claims, "complete")            # stops after the match, before completing
    with pytest.raises(LambdaKilled):
        service.reconcile(line("L1", "100.00", reference=sid("S1")))
    clock.advance(rs.LINE_CLAIM_LEASE_SECONDS + 1)
    result = service.reconcile(line("L1", "100.00", reference=sid("S1")))
    assert result == {"line_id": "L1", "status": "MATCHED", "match_type": "EXACT", "settlement_ids": [sid("S1")]}
    assert service.claims.state_of("L1", TENANT) == "SUCCEEDED"


def test_an_exception_written_before_the_invocation_stopped_is_reported_not_triaged_again(
        service, clock, monkeypatch):
    stop_once(monkeypatch, service.claims, "complete")
    with pytest.raises(LambdaKilled):
        service.reconcile(line("L9", "70.00"))                     # no open item: an exception
    runs = {"n": 0}
    real_run = service.agent.run
    monkeypatch.setattr(service.agent, "run", lambda *a, **k: (runs.__setitem__("n", runs["n"] + 1), real_run(*a, **k)))
    clock.advance(rs.LINE_CLAIM_LEASE_SECONDS + 1)
    result = service.reconcile(line("L9", "70.00"))
    assert result["status"] == "EXCEPTION" and result["kind"] == "UNMATCHED" and runs["n"] == 0


def test_an_error_releases_the_claim_for_the_next_delivery(service, feed, monkeypatch):
    feed.completed("S1", "100.00")
    service.poll_settlements()
    real = service.matcher.decide
    monkeypatch.setattr(service.matcher, "decide", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("DSA down")))
    with pytest.raises(RuntimeError):
        service.reconcile(line("L1", "100.00", reference=sid("S1")))
    assert service.claims.state_of("L1", TENANT) == "FAILED_RETRYABLE"
    monkeypatch.setattr(service.matcher, "decide", real)
    assert service.reconcile(line("L1", "100.00", reference=sid("S1")))["status"] == "MATCHED"


def test_the_same_line_id_with_other_content_is_a_conflict(service, feed):
    feed.completed("S1", "100.00")
    service.poll_settlements()
    service.reconcile(line("L1", "100.00", reference=sid("S1")))
    with pytest.raises(LineConflict):
        service.reconcile(line("L1", "999.00", reference=sid("S1")))
    [result] = DirectLineQueue(service.reconcile).submit([line("L1", "999.00", reference=sid("S1"))])
    assert result["status"] == "CONFLICT"


def test_the_claim_lives_in_the_service_table_under_e2a_partitions(service, table):
    service.reconcile(line("L5", "10.00"))
    item = table.get_item(Key={"pk": f"E2A#IDEM#{TENANT}#L5", "sk": "idem"})["Item"]
    assert item["state"] == "SUCCEEDED"


def test_lease_seconds_fit_the_lambda_and_queue_timeouts():
    import re
    from pathlib import Path
    tf = (Path(__file__).parents[1] / "infra" / "main.tf").read_text()
    lambda_timeout = int(re.search(r"\btimeout\s*=\s*(\d+)", tf).group(1))
    visibility = int(re.search(r"visibility_timeout_seconds\s*=\s*(\d+)", tf).group(1))
    assert lambda_timeout < rs.LINE_CLAIM_LEASE_SECONDS < visibility


class FakeLedger:
    def __init__(self):
        self.calls = []

    def post_adjustment(self, tenant_id, request):
        self.calls.append(request["key"])
        return {"outcome": "POSTED", "adjustment_id": "adj-1"}


def test_a_ledger_retry_while_another_run_holds_the_lease_posts_nothing(service, feed, clock):
    service.ledger = FakeLedger()
    feed.completed("S1", "250.00")
    service.poll_settlements()
    service.reconcile(line("L1", "247.50"))
    case = service.repo.get_exception(TENANT, "L1")
    case.status, case.ledger_status = "RESOLVED", "PENDING"
    case.ledger_request = {"key": f"recon-{TENANT}-L1", "type": "WRITE_OFF"}
    service.repo.put_exception(TENANT, case)

    other_run = service.lease.acquire(f"ledger-retry#{TENANT}", 60)
    assert service.retry_ledger_postings() == 0 and service.ledger.calls == []
    service.lease.release(other_run)
    assert service.retry_ledger_postings() == 1 and service.ledger.calls == [f"recon-{TENANT}-L1"]
    assert service.lease.acquire(f"ledger-retry#{TENANT}", 60), "the run released its lease"
