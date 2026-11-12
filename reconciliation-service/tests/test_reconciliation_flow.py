"""End to end against moto DynamoDB: feed -> open items -> bank lines -> matches and exceptions."""
from decimal import Decimal

import pytest
from e2a_simulated_llm import SimulatedLLMService, always

from conftest import sid, ACCOUNT, TENANT, line
from reconciliation_service.models.records import Proposal
from reconciliation_service.services.recon_service import ConcurrentChange, ProposalRejected


def test_poll_is_idempotent_and_keeps_a_durable_cursor(service, feed):
    feed.completed("S1", "100.00")
    feed.completed("S2", "50.00", minutes=1)
    assert service.poll_settlements() == 2
    assert service.poll_settlements() == 0                      # nothing new after the cursor
    assert service.repo.get_cursor(TENANT) == 2
    assert service.ingest_settlement_event(feed.events[0]) is False   # replayed event: no second item
    assert len(service.repo.open_items(TENANT, ACCOUNT, "EUR")) == 2


def test_exact_match_and_redelivery(service, feed):
    feed.completed("S1", "100.00")
    service.poll_settlements()
    result = service.reconcile(line("L1", "100.00", reference=sid("S1")))
    assert result["status"] == "MATCHED" and result["match_type"] == "EXACT"
    assert service.repo.get_open_item(TENANT, ACCOUNT, sid("S1")).status == "MATCHED"
    assert service.reconcile(line("L1", "100.00", reference=sid("S1")))["status"] == "ALREADY_RECEIVED"


def test_many_to_one_payment(service, feed):
    for name, amount, m in (("S1", "40.00", 0), ("S2", "60.00", 1), ("S3", "25.00", 2)):
        feed.completed(name, amount, m)
    service.poll_settlements()
    result = service.reconcile(line("L1", "100.00"))
    assert result["match_type"] == "SUBSET" and sorted(result["settlement_ids"]) == sorted([sid("S1"), sid("S2")])
    assert service.repo.get_open_item(TENANT, ACCOUNT, sid("S3")).status == "OPEN"


def test_duplicate_payment_gets_a_valid_refund_proposal(service, feed):
    feed.completed("S1", "100.00")
    service.poll_settlements()
    service.reconcile(line("L1", "100.00", txn="T-1"))
    result = service.reconcile(line("L2", "100.00", txn="T-1", day=4))
    assert (result["kind"], result["proposal"]["action"], result["agent_proposal_valid"]) == \
           ("DUPLICATE", "REFUND_DUPLICATE", True)
    assert service.accept("L2")["status"] == "RESOLVED"
    assert service.repo.get_line(TENANT, "L2")["status"] == "REFUND_REQUESTED"


def test_short_payment_within_the_limit_is_matched_with_write_off(service, feed):
    feed.completed("S1", "250.00")
    service.poll_settlements()
    result = service.reconcile(line("L1", "247.50"))             # 2.50 bank fee
    assert result["proposal"]["action"] == "MATCH_WITH_WRITE_OFF" and result["agent_proposal_valid"]
    accepted = service.accept("L1")
    assert accepted["status"] == "RESOLVED" and "2.50" in accepted["resolution"]
    assert service.repo.get_open_item(TENANT, ACCOUNT, sid("S1")).status == "MATCHED"


def test_agent_write_off_beyond_the_limit_is_refused_by_the_rules(service, feed):
    feed.completed("S1", "1000.00")
    service.poll_settlements()
    result = service.reconcile(line("L1", "985.00"))             # 1.5 %: the model proposes, the rules refuse
    case = service.repo.get_exception(TENANT, "L1")
    assert case.agent_proposal.action == "MATCH_WITH_WRITE_OFF"
    assert result["agent_proposal_valid"] is False and "write-off limit" in case.validation_reason
    assert case.proposal.action == "REQUEST_REMITTANCE"
    assert service.accept("L1")["status"] == "WAITING_REMITTANCE"
    assert service.repo.get_open_item(TENANT, ACCOUNT, sid("S1")).status == "OPEN"


def test_accept_revalidates_against_current_state(service, feed):
    feed.completed("S1", "250.00")
    service.poll_settlements()
    service.reconcile(line("L1", "248.00"))                      # proposal: write off 2.00 against S1
    service.reconcile(line("L2", "250.00"))                      # S1 is matched by another payment meanwhile
    with pytest.raises(ProposalRejected, match="OPEN"):
        service.accept("L1")


def test_concurrent_change_between_validation_and_execution(service, feed, monkeypatch):
    feed.completed("S1", "250.00")
    service.poll_settlements()
    service.reconcile(line("L1", "248.00"))
    monkeypatch.setattr(service.repo, "match", lambda *a, **k: False)   # the conditional write loses the race
    with pytest.raises(ConcurrentChange):
        service.accept("L1")
    assert service.repo.get_exception(TENANT, "L1").status == "OPEN"


def test_invalid_model_output_falls_back_to_remittance(service, feed):
    service.llm = SimulatedLLMService().add_rule("garbage", always(), "certainly! here is my answer")
    feed.completed("S1", "70.00")
    service.poll_settlements()
    result = service.reconcile(line("L1", "500.00"))
    assert result["kind"] == "UNMATCHED" and result["proposal"]["action"] == "REQUEST_REMITTANCE"


def test_refund_is_refused_for_a_non_duplicate(service, feed):
    feed.completed("S1", "70.00")
    service.poll_settlements()
    service.reconcile(line("L1", "500.00"))
    case = service.repo.get_exception(TENANT, "L1")
    valid, reason = service.validate(line("L1", "500.00"), case, Proposal(action="REFUND_DUPLICATE"))
    assert not valid and "duplicate" in reason
