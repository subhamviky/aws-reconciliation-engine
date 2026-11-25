"""Firestore repository (hub design note GCP-01): the same operations and guarantees as the
DynamoDB repository (repository.py), on Google Cloud's Always Free Firestore.

Every state change is conditional. Matching several open items is ONE Firestore transaction:
it reads every item and the line inside the transaction and commits only if each item is still
OPEN at the version the caller saw and the line is still RECEIVED or EXCEPTION; otherwise it
returns False and writes nothing. Firestore retries a transaction that lost a race; the retry
reads the winner's state and returns False, so an item is never matched twice.

Under heavy contention every contender can exhaust the client's attempts (it retries at once,
with no pause), and then nobody wins. _contended() runs the transaction again with a jittered,
growing pause, a bounded number of times: a transaction that failed to commit wrote nothing, so
running it again is safe; the last failure is raised (the message is redelivered).

Collections (one free database is shared by the landscape, so each takes a prefix):
  <prefix>_open        <tenant>#<account>#<settlement_id>   open item (expected cash)
  <prefix>_lines       <tenant>#<line_id>                   bank statement line
  <prefix>_exceptions  <tenant>#<line_id>                   exception case
  <prefix>_cursors     <tenant>#settlement-feed             position in the settlement event feed
Ids are percent-encoded (a Firestore id cannot contain "/").
"""
import json
import random
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from ..models.records import BankLine, ExceptionCase, OpenItem


CONTENDED_ROUNDS = 8


def _is_lost_commit(error: Exception) -> bool:
    from google.api_core.exceptions import Aborted, Conflict
    return isinstance(error, (Aborted, Conflict)) or (isinstance(error, ValueError) and "commit" in str(error).lower())


def _contended(attempt, rounds: int = CONTENDED_ROUNDS, sleep=time.sleep):
    """Run attempt() again after a jittered pause when its transaction could not commit."""
    from google.api_core.exceptions import Aborted, Conflict
    for n in range(rounds):
        try:
            return attempt()
        except (Aborted, Conflict, ValueError) as e:
            if isinstance(e, ValueError) and "commit" not in str(e).lower():
                raise                                         # not a lost race: a real error
            if n == rounds - 1:
                raise
            sleep(random.uniform(0.0, min(1.0, 0.025 * (2 ** n))))


def _id(*parts: str) -> str:
    return "#".join(quote(str(p), safe="") for p in parts)


class FirestoreReconRepository:
    backend = "firestore"

    def __init__(self, client, prefix: str = "recon") -> None:
        self.client, self.prefix = client, prefix
        self._open = client.collection(f"{prefix}_open")
        self._lines = client.collection(f"{prefix}_lines")
        self._exceptions = client.collection(f"{prefix}_exceptions")
        self._cursors = client.collection(f"{prefix}_cursors")

    # E2A claims and the ledger-retry lease live next to the data (same database, own collection)
    def idempotency_store(self, **kwargs):
        from e2a_adapters.gcp import FirestoreIdempotencyStore
        return FirestoreIdempotencyStore(self.client, collection=f"{self.prefix}_e2a", **kwargs)

    def lease_store(self, **kwargs):
        from e2a_adapters.gcp import FirestoreLease
        return FirestoreLease(self.client, collection=f"{self.prefix}_e2a", **kwargs)

    # ------------------------------------------------------------ open items
    def add_open_item(self, tenant: str, item: OpenItem) -> bool:
        """Idempotent: a settlement event delivered twice creates one open item."""
        return self._create(self._open.document(_id(tenant, item.account, item.settlement_id)),
                            {"tenant": tenant, **json.loads(item.model_dump_json())})

    def open_items(self, tenant: str, account: str, currency: str) -> List[OpenItem]:
        docs = self._where(self._open, tenant, account=account)
        return sorted((OpenItem.model_validate(d) for d in docs if d["status"] == "OPEN" and d["currency"] == currency),
                      key=lambda i: (i.settled_at, i.settlement_id))

    def get_open_item(self, tenant: str, account: str, settlement_id: str) -> Optional[OpenItem]:
        snap = self._open.document(_id(tenant, account, settlement_id)).get()
        return OpenItem.model_validate(snap.to_dict()) if snap.exists else None

    # ----------------------------------------------------------------- lines
    def add_line(self, tenant: str, line: BankLine) -> bool:
        """Idempotent ingestion: the same line_id is stored once."""
        return self._create(self._lines.document(_id(tenant, line.line_id)),
                            {"tenant": tenant, "status": "RECEIVED", **json.loads(line.model_dump_json())})

    def get_line(self, tenant: str, line_id: str) -> Optional[Dict[str, Any]]:
        snap = self._lines.document(_id(tenant, line_id)).get()
        return self._plain(snap.to_dict()) if snap.exists else None

    def lines(self, tenant: str) -> List[Dict[str, Any]]:
        return [self._plain(d) for d in self._where(self._lines, tenant)]

    def set_line_status(self, tenant: str, line_id: str, status: str) -> None:
        self._lines.document(_id(tenant, line_id)).set({"status": status}, merge=True)

    def match(self, tenant: str, line: BankLine, items: List[OpenItem], match_type: str,
              write_off: Decimal = Decimal("0.00")) -> bool:
        """Match a line to one or more open items in ONE transaction. False when any item is no
        longer OPEN at its expected version, or the line is already matched; nothing is written."""
        from google.cloud import firestore
        item_refs = [self._open.document(_id(tenant, i.account, i.settlement_id)) for i in items]
        line_ref = self._lines.document(_id(tenant, line.line_id))

        @firestore.transactional
        def run(transaction) -> bool:
            snaps = [ref.get(transaction=transaction) for ref in item_refs]       # every read before any write
            line_snap = line_ref.get(transaction=transaction)
            for item, snap in zip(items, snaps):
                data = snap.to_dict() if snap.exists else None
                if not data or data.get("status") != "OPEN" or int(data.get("version", 0)) != item.version:
                    return False
            if not line_snap.exists or (line_snap.to_dict() or {}).get("status") not in ("RECEIVED", "EXCEPTION"):
                return False
            for item, ref in zip(items, item_refs):
                transaction.update(ref, {"status": "MATCHED", "version": item.version + 1,
                                         "matched_line": line.line_id})
            transaction.update(line_ref, {"status": "MATCHED", "match_type": match_type,
                                          "matched_settlements": [i.settlement_id for i in items],
                                          "write_off": str(write_off)})
            return True

        try:
            return _contended(lambda: run(self.client.transaction()))
        except Exception as contention:
            if not _is_lost_commit(contention):
                raise
            # Every attempt lost its lock race. If the winner has committed, this match lost: say so (it may
            # need a moment to be visible).
            for look in range(6):
                snaps = [ref.get() for ref in item_refs]
                taken = any(not (snap.exists and (snap.to_dict() or {}).get("status") == "OPEN"
                                 and int((snap.to_dict() or {}).get("version", 0)) == item.version)
                            for item, snap in zip(items, snaps))
                line_snap = line_ref.get()
                done = not line_snap.exists or (line_snap.to_dict() or {}).get("status") not in ("RECEIVED", "EXCEPTION")
                if taken or done:
                    return False
                time.sleep(0.25 * (look + 1))
            raise                                            # still open: not a lost race; the message is redelivered

    # ------------------------------------------------------------ exceptions
    def put_exception(self, tenant: str, case: ExceptionCase) -> None:
        self._exceptions.document(_id(tenant, case.line_id)).set({"tenant": tenant, **json.loads(case.model_dump_json())})

    def get_exception(self, tenant: str, line_id: str) -> Optional[ExceptionCase]:
        snap = self._exceptions.document(_id(tenant, line_id)).get()
        return ExceptionCase.model_validate(self._plain(snap.to_dict())) if snap.exists else None

    def exceptions(self, tenant: str) -> List[ExceptionCase]:
        return [ExceptionCase.model_validate(self._plain(d)) for d in self._where(self._exceptions, tenant)]

    # ---------------------------------------------------------------- cursor
    def get_cursor(self, tenant: str) -> int:
        snap = self._cursors.document(_id(tenant, "settlement-feed")).get()
        return int(snap.to_dict()["position"]) if snap.exists else 0

    def advance_cursor(self, tenant: str, old: int, new: int) -> bool:
        """Moves forward only, and only from the position the caller read."""
        from google.cloud import firestore
        ref = self._cursors.document(_id(tenant, "settlement-feed"))

        @firestore.transactional
        def run(transaction) -> bool:
            snap = ref.get(transaction=transaction)
            if snap.exists and int(snap.to_dict()["position"]) != old:
                return False
            transaction.set(ref, {"tenant": tenant, "position": new})
            return True

        return _contended(lambda: run(self.client.transaction()))

    # --------------------------------------------------------------- helpers
    @staticmethod
    def _create(ref, data: Dict[str, Any]) -> bool:
        from google.api_core.exceptions import AlreadyExists, Conflict
        try:
            ref.create(data)
            return True
        except (AlreadyExists, Conflict):
            return False

    @staticmethod
    def _where(collection, tenant: str, **equals) -> List[Dict[str, Any]]:
        from google.cloud.firestore_v1.base_query import FieldFilter
        query = collection.where(filter=FieldFilter("tenant", "==", tenant))
        for field, value in equals.items():
            query = query.where(filter=FieldFilter(field, "==", value))
        return [d.to_dict() for d in query.stream()]

    @staticmethod
    def _plain(data: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """The stored record without the partition field, as the DynamoDB repository returns it."""
        return {k: v for k, v in (data or {}).items() if k != "tenant"} or None
