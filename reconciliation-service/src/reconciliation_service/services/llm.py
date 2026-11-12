"""Model boundary: E2A SimulatedLLMService (no model access).

The rule behaves like a helpful but unreliable model: it proposes a write-off for
the nearest candidate whenever the difference is within 2 % of the amount, even
when that exceeds the write-off limit only the deterministic rules know. That is
exactly the case the confirmation step must catch.
"""
import json
import re
from decimal import Decimal

from e2a_simulated_llm import SimulatedLLMService, system_contains

AGENT_MARKER = "exception triage agent"


def _propose(messages, ctx) -> str:
    user = str(messages[-1].get("content", ""))
    kind = re.search(r"^Exception: (\w+)", user, re.M).group(1)
    amount = Decimal(re.search(r"^Line amount: ([0-9.]+)", user, re.M).group(1))
    candidates = [(sid, Decimal(amt)) for sid, amt in re.findall(r"^- candidate (\S+) amount ([0-9.]+)", user, re.M)]
    if kind == "DUPLICATE":
        return json.dumps({"action": "REFUND_DUPLICATE", "settlement_ids": [],
                           "rationale": "The payment repeats one already received; return it to the payer."})
    if candidates:
        sid, nearest = min(candidates, key=lambda c: abs(c[1] - amount))
        if abs(nearest - amount) <= amount * Decimal("0.02"):
            return json.dumps({"action": "MATCH_WITH_WRITE_OFF", "settlement_ids": [sid],
                               "rationale": f"Closest open item {sid} differs by {abs(nearest - amount)}; "
                                            "likely a bank fee or short payment."})
    return json.dumps({"action": "REQUEST_REMITTANCE", "settlement_ids": [],
                       "rationale": "No open item explains the amount; ask the payer for remittance advice."})


def build_triage_llm() -> SimulatedLLMService:
    return SimulatedLLMService().add_rule("triage:propose", system_contains(AGENT_MARKER), _propose)
