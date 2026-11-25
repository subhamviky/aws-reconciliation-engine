"""GCP-01: the Firestore repository keeps the DynamoDB repository's guarantees, on the Firestore
emulator (skipped without FIRESTORE_EMULATOR_HOST; the CI runs it)."""
import os
import threading
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from conftest import ACCOUNT, TENANT, firestore_repository, line, sid
from reconciliation_service.models.records import ExceptionCase, OpenItem

pytestmark = pytest.mark.skipif(not os.getenv("FIRESTORE_EMULATOR_HOST"),
                                reason="FIRESTORE_EMULATOR_HOST not set (Firestore emulator not running)")


def item(name, amount="100.00", version=0):
    return OpenItem(settlement_id=sid(name), account=ACCOUNT, amount=Decimal(amount), currency="EUR",
                    settled_at=datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc), version=version)


def test_ingestion_is_idempotent_and_reads_back_what_dynamodb_would():
    repo = firestore_repository()
    assert repo.add_open_item(TENANT, item("S1")) and not repo.add_open_item(TENANT, item("S1"))
    assert repo.add_line(TENANT, line("L1", "100.00")) and not repo.add_line(TENANT, line("L1", "100.00"))
    assert [i.settlement_id for i in repo.open_items(TENANT, ACCOUNT, "EUR")] == [sid("S1")]
    assert repo.open_items(TENANT, ACCOUNT, "USD") == [] and repo.open_items("other", ACCOUNT, "EUR") == []
    stored = repo.get_line(TENANT, "L1")
    assert stored["status"] == "RECEIVED" and stored["line_id"] == "L1" and "tenant" not in stored


def test_a_match_is_one_transaction_and_a_stale_version_writes_nothing():
    repo = firestore_repository()
    repo.add_open_item(TENANT, item("S1", "60.00"))
    repo.add_open_item(TENANT, item("S2", "40.00"))
    repo.add_line(TENANT, line("L1", "100.00"))
    stale = [item("S1", "60.00"), item("S2", "40.00", version=7)]
    assert not repo.match(TENANT, line("L1", "100.00"), stale, "MANY_TO_ONE")
    assert repo.get_open_item(TENANT, ACCOUNT, sid("S1")).status == "OPEN"            # nothing half-matched
    assert repo.match(TENANT, line("L1", "100.00"), [item("S1", "60.00"), item("S2", "40.00")], "MANY_TO_ONE")
    s1 = repo.get_open_item(TENANT, ACCOUNT, sid("S1"))
    assert s1.status == "MATCHED" and s1.version == 1
    assert repo.get_line(TENANT, "L1")["matched_settlements"] == [sid("S1"), sid("S2")]
    assert not repo.match(TENANT, line("L1", "100.00"), [item("S1", "60.00", version=1)], "EXACT")   # line done


def test_concurrent_matches_of_one_item_have_exactly_one_winner():
    repo = firestore_repository()
    repo.add_open_item(TENANT, item("S1"))
    for n in range(8):
        repo.add_line(TENANT, line(f"L{n}", "100.00"))
    results, barrier = [None] * 8, threading.Barrier(8)

    def worker(n):
        barrier.wait()
        try:
            results[n] = repo.match(TENANT, line(f"L{n}", "100.00"), [item("S1")], "EXACT")
        except Exception as e:                                # shown in the assertion, not lost in a thread
            results[n] = e
    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert results.count(True) == 1 and results.count(False) == 7, results
    winner = results.index(True)
    assert repo.get_open_item(TENANT, ACCOUNT, sid("S1")).version == 1
    assert [n for n in range(8) if repo.get_line(TENANT, f"L{n}")["status"] == "MATCHED"] == [winner]


def test_exceptions_and_the_feed_cursor():
    repo = firestore_repository()
    repo.put_exception(TENANT, ExceptionCase(line_id="L1", kind="UNMATCHED", detail="no open item"))
    assert repo.get_exception(TENANT, "L1").kind == "UNMATCHED"
    assert [c.line_id for c in repo.exceptions(TENANT)] == ["L1"]
    assert repo.get_cursor(TENANT) == 0
    assert repo.advance_cursor(TENANT, 0, 5) and not repo.advance_cursor(TENANT, 0, 9)  # only from what was read
    assert repo.get_cursor(TENANT) == 5


def test_claims_and_the_lease_are_firestore_stores_next_to_the_data():
    repo = firestore_repository()
    assert type(repo.idempotency_store()).__name__ == "FirestoreIdempotencyStore"
    assert type(repo.lease_store()).__name__ == "FirestoreLease"
