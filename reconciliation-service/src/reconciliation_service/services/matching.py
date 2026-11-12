"""Deterministic matching with governed DSA calls.

1. EXACT   the line's reference is an open settlement id with the same amount
2. FIFO    the oldest open item with exactly the line's amount
3. SUBSET  several open items that add up to exactly the line's amount (many-to-one):
           one DSA SUBSET_SUM call finds the smallest such set (ties: the oldest items),
           on the amounts as Decimals with scale 2. A search stopped by its bound is
           AMBIGUOUS, never "no match": DSA says so (complete=False), and it is honoured.
Duplicates are the line's group in DSA UNION_FIND GROUP_BY_KEYS (lines that share a key).
"""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional

from capability_oriented_dsa import DSAFacade, SequenceState, UnionFindState

from ..models.records import BankLine, OpenItem


@dataclass
class MatchDecision:
    match_type: Optional[str]                    # EXACT | FIFO | SUBSET | None
    items: List[OpenItem] = field(default_factory=list)
    ambiguous: bool = False
    reason: str = ""


class Matcher:
    def __init__(self, max_candidates: int = 9, max_nodes: int = 10000) -> None:
        self.max_candidates, self.max_nodes = max_candidates, max_nodes
        self.dsa = DSAFacade()

    def decide(self, line: BankLine, open_items: List[OpenItem]) -> MatchDecision:
        items = [i for i in open_items if i.currency == line.currency and i.status == "OPEN"]
        if line.reference:
            referenced = [i for i in items if i.settlement_id == line.reference and i.amount == line.amount]
            if referenced:
                return MatchDecision("EXACT", referenced[:1], reason="reference and amount")
        equal = [i for i in items if i.amount == line.amount]
        if equal:
            return MatchDecision("FIFO", equal[:1], reason="oldest open item with the same amount")
        return self._subset(line, [i for i in items if i.amount < line.amount])

    def _subset(self, line: BankLine, smaller: List[OpenItem]) -> MatchDecision:
        if len(smaller) < 2:
            return MatchDecision(None, reason="no combination of open items")
        candidates = smaller[: self.max_candidates]
        result = self.dsa.execute(structure_type="SEQUENCE", capability="OPTIMIZATION", operation="SUBSET_SUM",
                                  state=SequenceState([i.amount for i in candidates]), target=line.amount, scale=2,
                                  max_nodes=self.max_nodes)
        if not result.complete:
            return MatchDecision(None, ambiguous=True, reason="search stopped at its bound before an answer")
        if not result.found:
            if len(smaller) > len(candidates):
                return MatchDecision(None, ambiguous=True,
                                     reason=f"no exact combination among the {len(candidates)} oldest of "
                                            f"{len(smaller)} candidate items")
            return MatchDecision(None, reason="no combination of open items adds up to the amount")
        return MatchDecision("SUBSET", [candidates[i] for i in result.data],
                             reason=f"{len(result.data)} open items add up to the amount")

    def nearest(self, amount: Decimal, items: List[OpenItem], count: int = 3) -> List[OpenItem]:
        """Open items with the closest amounts (DSA LOWER_BOUND on the sorted amounts)."""
        ordered = sorted(items, key=lambda i: i.amount)
        if not ordered:
            return []
        index = self.dsa.execute(structure_type="SEQUENCE", capability="SEARCH", operation="LOWER_BOUND",
                                 state=SequenceState(ordered), target=amount, key=lambda i: i.amount).data
        window = ordered[max(0, index - count):index + count]
        return sorted(window, key=lambda i: (abs(i.amount - amount), i.settled_at))[:count]


def payment_keys(line: Dict) -> list:
    """Two lines are the same payment when they share the bank transaction id, or all of
    amount, currency, value date, counterparty account and reference."""
    fields = ("amount", "currency", "value_date", "counterparty_account", "reference")
    return [("txn", line["bank_txn_id"]), ("fields",) + tuple(str(line.get(f)) for f in fields)]


def duplicate_of(new_line: Dict, existing: List[Dict], dsa: DSAFacade = None) -> Optional[str]:
    """The earliest existing line in the new line's duplicate group (DSA GROUP_BY_KEYS), if any."""
    dsa = dsa or DSAFacade()
    lines = [l for l in existing if l["line_id"] != new_line["line_id"]] + [new_line]
    groups = dsa.execute(structure_type="UNION_FIND", capability="MUTATION", operation="GROUP_BY_KEYS",
                         state=UnionFindState(), elements=lines, keys=payment_keys,
                         element_id=lambda l: l["line_id"]).data
    group = next(g for g in groups if any(l["line_id"] == new_line["line_id"] for l in g))
    earlier = sorted((l for l in group if l["line_id"] != new_line["line_id"]),
                     key=lambda l: (str(l["value_date"]), l["line_id"]))
    return earlier[0]["line_id"] if earlier else None
