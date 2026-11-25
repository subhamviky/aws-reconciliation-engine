"""GCP-01: a Firestore transaction that could not commit (every attempt lost a race) is run again
after a jittered pause, a bounded number of times; other errors are not retried. No emulator."""
import pytest
from google.api_core.exceptions import Aborted

from reconciliation_service.services.repository_firestore import _contended


def test_a_transaction_that_lost_every_race_runs_again_until_it_commits():
    outcomes, pauses = [ValueError("Failed to commit transaction in 5 attempts."), Aborted("contention"), True], []

    def attempt():
        result = outcomes.pop(0)
        if isinstance(result, Exception):
            raise result
        return result
    assert _contended(attempt, sleep=pauses.append) is True
    assert len(pauses) == 2 and all(0 <= p <= 1.0 for p in pauses)


def test_the_last_failure_is_raised_after_the_bounded_rounds():
    calls = []

    def attempt():
        calls.append(1)
        raise Aborted("contention")
    with pytest.raises(Aborted):
        _contended(attempt, rounds=3, sleep=lambda s: None)
    assert len(calls) == 3


def test_a_real_error_is_not_retried():
    calls = []

    def attempt():
        calls.append(1)
        raise ValueError("bad document")
    with pytest.raises(ValueError, match="bad document"):
        _contended(attempt, sleep=lambda s: None)
    assert calls == [1]


def test_a_match_that_lost_every_lock_race_reports_false_once_the_winner_has_committed():
    from decimal import Decimal
    from datetime import datetime, timezone
    from unittest.mock import MagicMock

    from reconciliation_service.models.records import BankLine, OpenItem
    from reconciliation_service.services import repository_firestore as module
    from reconciliation_service.services.repository_firestore import FirestoreReconRepository

    taken = MagicMock(exists=True)
    taken.to_dict.return_value = {"status": "MATCHED", "version": 1}
    client = MagicMock()
    client.collection.return_value.document.return_value.get.return_value = taken
    repo = FirestoreReconRepository.__new__(FirestoreReconRepository)
    repo.client, repo._open, repo._lines = client, client.collection(), client.collection()
    item = OpenItem(settlement_id="s1", account="A", amount=Decimal("1.00"), currency="EUR",
                    settled_at=datetime(2026, 11, 2, tzinfo=timezone.utc), version=0)
    line = BankLine(line_id="L", bank_txn_id="T", value_date="2026-11-02", amount=Decimal("1.00"), currency="EUR",
                    counterparty_account="A", reference=None)
    original = module._contended
    module._contended = lambda attempt, **kw: (_ for _ in ()).throw(ValueError("Failed to commit transaction in 5 attempts."))
    try:
        assert repo.match("acme", line, [item], "EXACT") is False
    finally:
        module._contended = original
