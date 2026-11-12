"""Reconciliation: expected cash (open items from settlement events) against actual
cash (bank lines). Every material change goes through the repository's conditional
writes; the triage agent only proposes, and accept() re-validates before executing.
"""
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from e2a_simulated_llm import SimulatedLLMService

from ..agents.exception_triage_agent import ExceptionTriageAgent
from ..models.records import BankLine, ExceptionCase, OpenItem, Proposal
from .matching import Matcher, duplicate_of
from .repository import ReconRepository
from .settlement_client import SettlementFeed, events_from


class ProposalRejected(Exception):
    """The rules refuse the proposal against the current state (HTTP 422)."""


class ConcurrentChange(Exception):
    """An item changed between validation and execution (HTTP 409)."""


class ReconciliationService:
    def __init__(self, repo: ReconRepository, feed: SettlementFeed, llm: SimulatedLLMService, tenant_id: str,
                 matcher: Matcher = None, write_off_limit: Decimal = Decimal("5.00")) -> None:
        self.repo, self.feed, self.llm, self.tenant = repo, feed, llm, tenant_id
        self.matcher = matcher or Matcher()
        self.write_off_limit = write_off_limit
        self.agent = ExceptionTriageAgent()

    # ------------------------------------------------- expected cash (feed)
    def poll_settlements(self) -> int:
        position = self.repo.get_cursor(self.tenant)
        feed = self.feed.events_after(self.tenant, position)
        ingested = sum(1 for e in events_from(feed) if self.ingest_settlement_event(e))
        new_position = int(feed.get("next_after_sequence", position))
        if new_position > position:
            self.repo.advance_cursor(self.tenant, position, new_position)
        return ingested

    def ingest_settlement_event(self, event: Dict) -> bool:
        if event["event_type"] != "settlement.completed":
            return False
        s = event["settlement"]
        return self.repo.add_open_item(self.tenant, OpenItem(
            settlement_id=s["settlement_id"], account=s["payee_account"], amount=Decimal(s["amount"]),
            currency=s["currency"], settled_at=datetime.fromisoformat(event["occurred_at"])))

    # --------------------------------------------------- actual cash (lines)
    def reconcile(self, line: BankLine) -> Dict:
        if not self.repo.add_line(self.tenant, line):
            return {"line_id": line.line_id, "status": "ALREADY_RECEIVED"}       # redelivery: no effect
        existing = self.repo.lines(self.tenant)
        original = duplicate_of(line.model_dump(mode="json"), existing)
        if original:
            return self._exception(line, "DUPLICATE", f"same payment as line {original}", [], original)

        items = self.repo.open_items(self.tenant, line.counterparty_account, line.currency)
        decision = self.matcher.decide(line, items)
        if decision.match_type and self.repo.match(self.tenant, line, decision.items, decision.match_type):
            return {"line_id": line.line_id, "status": "MATCHED", "match_type": decision.match_type,
                    "settlement_ids": [i.settlement_id for i in decision.items]}
        kind = "AMBIGUOUS" if decision.ambiguous else "UNMATCHED"
        return self._exception(line, kind, decision.reason or "matched items changed concurrently",
                               self.matcher.nearest(line.amount, items))

    # ------------------------------------------------------------ exceptions
    def _exception(self, line: BankLine, kind: str, detail: str, candidates: List[OpenItem],
                   duplicate: Optional[str] = None) -> Dict:
        state = {"tenant_id": self.tenant, "kind": kind, "detail": detail,
                 "line": line.model_dump(mode="json"),
                 "candidates": [c.model_dump(mode="json") for c in candidates]}
        config = {"llm_service": self.llm, "min_confidence": 0.5, "max_latency": 5.0}
        self.agent.run(state, config, tenant_id=self.tenant, idempotency_key=line.line_id)
        proposal: Proposal = state["proposal"]
        case = ExceptionCase(line_id=line.line_id, kind=kind, detail=detail, candidates=candidates,
                             duplicate_of=duplicate, agent_proposal=proposal)
        valid, reason = self.validate(line, case, proposal)
        case.agent_proposal_valid, case.validation_reason = valid, reason
        case.proposal = proposal if valid else Proposal(
            action="REQUEST_REMITTANCE", rationale=f"agent proposal refused by the rules: {reason}")
        self.repo.put_exception(self.tenant, case)
        self.repo.set_line_status(self.tenant, line.line_id, "EXCEPTION")
        return {"line_id": line.line_id, "status": "EXCEPTION", "kind": kind,
                "proposal": case.proposal.model_dump(), "agent_proposal_valid": valid}

    def validate(self, line: BankLine, case: ExceptionCase, proposal: Proposal) -> Tuple[bool, str]:
        """The deterministic authority over every proposal, checked against CURRENT state."""
        if proposal.action == "REQUEST_REMITTANCE":
            return True, "always allowed"
        if proposal.action == "REFUND_DUPLICATE":
            return (case.kind == "DUPLICATE"), ("duplicate payment" if case.kind == "DUPLICATE"
                                                else "a refund is only allowed for a duplicate payment")
        items = [self.repo.get_open_item(self.tenant, line.counterparty_account, sid) for sid in proposal.settlement_ids]
        if not items or any(i is None or i.status != "OPEN" or i.currency != line.currency for i in items):
            return False, "every proposed settlement must be an OPEN item of this account and currency"
        total = sum((i.amount for i in items), Decimal("0"))
        if proposal.action == "MATCH":
            return (total == line.amount), ("amounts agree" if total == line.amount
                                            else f"items add up to {total}, the line is {line.amount}")
        if len(items) != 1:
            return False, "a write-off match takes exactly one item"
        difference = abs(total - line.amount)
        if difference > self.write_off_limit:
            return False, f"difference {difference} exceeds the write-off limit {self.write_off_limit}"
        return True, f"difference {difference} within the write-off limit {self.write_off_limit}"

    def accept(self, line_id: str) -> Dict:
        """Execute the stored proposal: re-validate, execute conditionally, confirm."""
        case = self.repo.get_exception(self.tenant, line_id)
        raw_line = self.repo.get_line(self.tenant, line_id)
        if case is None or raw_line is None or case.status != "OPEN":
            raise ProposalRejected("no open exception for this line")
        line = BankLine.model_validate(raw_line)
        valid, reason = self.validate(line, case, case.proposal)
        if not valid:
            raise ProposalRejected(reason)
        action = case.proposal.action
        if action in ("MATCH", "MATCH_WITH_WRITE_OFF"):
            items = [self.repo.get_open_item(self.tenant, line.counterparty_account, sid)
                     for sid in case.proposal.settlement_ids]
            write_off = abs(sum((i.amount for i in items), Decimal("0")) - line.amount)
            if not self.repo.match(self.tenant, line, items, action, write_off):
                raise ConcurrentChange("an item changed since validation; nothing was matched")
            confirmed = all(self.repo.get_open_item(self.tenant, line.counterparty_account, i.settlement_id).status
                            == "MATCHED" for i in items)
            if not confirmed:                                   # deterministic confirmation of the effect
                raise ConcurrentChange("the match could not be confirmed")
            case.status, case.resolution = "RESOLVED", f"{action} (write-off {write_off})"
        elif action == "REFUND_DUPLICATE":
            self.repo.set_line_status(self.tenant, line_id, "REFUND_REQUESTED")
            case.status, case.resolution = "RESOLVED", "refund requested"
        else:
            case.status, case.resolution = "WAITING_REMITTANCE", "remittance advice requested"
        self.repo.put_exception(self.tenant, case)
        return {"line_id": line_id, "status": case.status, "resolution": case.resolution}

    # ---------------------------------------------------------------- reads
    def exceptions(self, status: Optional[str] = None) -> List[ExceptionCase]:
        cases = self.repo.exceptions(self.tenant)
        return [c for c in cases if status is None or c.status == status]
