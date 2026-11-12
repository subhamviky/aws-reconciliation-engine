"""Deterministic matching with governed DSA calls.

1. EXACT   the line's reference is an open settlement id with the same amount
2. FIFO    the oldest open item with exactly the line's amount
3. SUBSET  several open items that add up to exactly the line's amount (many-to-one):
           KNAPSACK_01 decides cheaply whether such a subset exists, then a bounded
           SUBSETS enumeration finds the smallest one. A truncated enumeration is
           AMBIGUOUS, never "no match": DSA says so, and the result must be honoured.
Duplicates are clusters found with UNION_FIND.
"""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional

from capability_oriented_dsa import DSAFacade, SequenceState, UnionFindState

from ..models.records import BankLine, OpenItem


def cents(amount: Decimal) -> int:
    return int((amount * 100).to_integral_value())


@dataclass
class MatchDecision:
    match_type: Optional[str]                    # EXACT | FIFO | SUBSET | None
    items: List[OpenItem] = field(default_factory=list)
    ambiguous: bool = False
    reason: str = ""


class Matcher:
    def __init__(self, max_candidates: int = 9, enumeration_limit: int = 1000) -> None:
        self.max_candidates, self.enumeration_limit = max_candidates, enumeration_limit
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
        values, target = [cents(i.amount) for i in candidates], cents(line.amount)
        best = self.dsa.execute(structure_type="SEQUENCE", capability="OPTIMIZATION", operation="KNAPSACK_01",
                                state=SequenceState([(v, v) for v in values]), capacity=target).data
        if best != target:
            if len(smaller) > len(candidates):
                return MatchDecision(None, ambiguous=True,
                                     reason=f"no exact combination among the {len(candidates)} oldest of "
                                            f"{len(smaller)} candidate items")
            return MatchDecision(None, reason="no combination of open items adds up to the amount")
        result = self.dsa.execute(structure_type="SEQUENCE", capability="ENUMERATION", operation="SUBSETS",
                                  state=SequenceState(list(range(len(candidates)))),
                                  enumeration_limit=self.enumeration_limit)
        if result.metadata.get("truncated"):
            return MatchDecision(None, ambiguous=True, reason="search truncated by the enumeration limit")
        exact = [s for s in result.data if s and sum(values[i] for i in s) == target]
        best_subset = min(exact, key=lambda s: (len(s), s))
        return MatchDecision("SUBSET", [candidates[i] for i in best_subset],
                             reason=f"{len(best_subset)} open items add up to the amount")

    def nearest(self, amount: Decimal, items: List[OpenItem], count: int = 3) -> List[OpenItem]:
        """Open items with the closest amounts (DSA LOWER_BOUND on the sorted amounts)."""
        ordered = sorted(items, key=lambda i: i.amount)
        if not ordered:
            return []
        index = self.dsa.execute(structure_type="SEQUENCE", capability="SEARCH", operation="LOWER_BOUND",
                                 state=SequenceState(ordered), target=amount, key=lambda i: i.amount).data
        window = ordered[max(0, index - count):index + count]
        return sorted(window, key=lambda i: (abs(i.amount - amount), i.settled_at))[:count]


def same_payment(a: Dict, b: Dict) -> bool:
    if a["bank_txn_id"] == b["bank_txn_id"]:
        return True
    fields = ("amount", "currency", "value_date", "counterparty_account", "reference")
    return all(str(a.get(f)) == str(b.get(f)) for f in fields)


def duplicate_of(new_line: Dict, existing: List[Dict], dsa: DSAFacade = None) -> Optional[str]:
    """The earliest existing line in the new line's duplicate cluster (DSA UNION_FIND), if any."""
    dsa = dsa or DSAFacade()
    lines = [l for l in existing if l["line_id"] != new_line["line_id"]] + [new_line]
    state = UnionFindState()
    for l in lines:
        dsa.execute(structure_type="UNION_FIND", capability="MUTATION", operation="ADD", state=state, element=l["line_id"])
    for i, a in enumerate(lines):
        for b in lines[i + 1:]:
            if same_payment(a, b):
                dsa.execute(structure_type="UNION_FIND", capability="MUTATION", operation="UNION",
                            state=state, left=a["line_id"], right=b["line_id"])
    for l in sorted(existing, key=lambda l: (str(l["value_date"]), l["line_id"])):
        if l["line_id"] != new_line["line_id"] and dsa.execute(
                structure_type="UNION_FIND", capability="QUERY", operation="CONNECTED", state=state,
                left=l["line_id"], right=new_line["line_id"]).data:
            return l["line_id"]
    return None
