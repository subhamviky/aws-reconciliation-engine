"""Records of the reconciliation domain. Money is always Decimal, never float."""
from datetime import date, datetime
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

ExceptionKind = Literal["UNMATCHED", "AMBIGUOUS", "DUPLICATE"]
Action = Literal["MATCH", "MATCH_WITH_WRITE_OFF", "REFUND_DUPLICATE", "REQUEST_REMITTANCE"]


class BankLine(BaseModel):
    """One credit on a bank statement (contracts/statements/bank-statement-line.v1.schema.json)."""
    line_id: str
    bank_txn_id: str
    value_date: date
    amount: Decimal
    currency: str
    counterparty_account: str
    reference: Optional[str] = None


class OpenItem(BaseModel):
    """Cash expected on an account because a settlement completed."""
    settlement_id: str
    account: str
    amount: Decimal
    currency: str
    settled_at: datetime
    status: Literal["OPEN", "MATCHED"] = "OPEN"
    version: int = 0


class Proposal(BaseModel):
    action: Action
    settlement_ids: List[str] = Field(default_factory=list)
    rationale: str = ""


class ExceptionCase(BaseModel):
    line_id: str
    kind: ExceptionKind
    detail: str
    candidates: List[OpenItem] = Field(default_factory=list)
    duplicate_of: Optional[str] = None
    agent_proposal: Optional[Proposal] = None
    agent_proposal_valid: Optional[bool] = None
    validation_reason: Optional[str] = None
    proposal: Optional[Proposal] = None          # what accept() will execute
    status: Literal["OPEN", "RESOLVED", "WAITING_REMITTANCE"] = "OPEN"
    resolution: Optional[str] = None
